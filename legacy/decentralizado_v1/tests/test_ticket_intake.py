"""Stage 1 real network with mocked dependencies; no PostgreSQL writes."""
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network
from app.agents.decentralized.ticket_intake import capture_ticket_request
from app.database.decentralized_repository import RetryConflict


def state(text, **fields):
    return dict(messages=[HumanMessage(content=text)],customer_id=1,request_revision=0,**fields)


@pytest.mark.parametrize("kind,details,target", [
    ("REPAIR","Equipo: laptop; Síntomas: no enciende","tecnico"),
    ("SUPPORT","Equipo: PC; Síntomas: error Windows","software"),
    ("SALE","Producto: SSD SATA 500GB; Cantidad: 2","ventas"),
    ("PC_BUILD","Uso: diseño; Presupuesto: 2500","ventas"),
    ("WARRANTY_CLAIM","Código: WAR-TEST; Motivo: se apaga","garantia")])
def test_five_types(kind,details,target):
    patch=capture_ticket_request(state("Solicitud: "+kind+"; "+details),authenticated_customer_id=1)
    assert patch["pending_ticket_operation"]["payload"]["request_type"] == kind
    assert len(patch["pending_ticket_operation"]["payload"]["code"]) == 20
    assert patch["next_agent"] == target
    assert not any(key in patch for key in ("ticket_id","ticket_code","ticket_status"))
    assert not patch["messages"][0].tool_calls


def test_progressive_correction_change_and_stable_retry():
    s=state("Quiero comprar; Producto: SSD SATA 500GB")
    first=capture_ticket_request(s,authenticated_customer_id=1)
    assert first["intake"]["missing_fields"] == ["quantity"]
    s.update(first,messages=[HumanMessage(content="Producto: SSD NVMe 1TB")])
    correction=capture_ticket_request(s,authenticated_customer_id=1)
    assert correction["request_revision"] == 1
    s.update(correction,messages=[HumanMessage(content="Solicitud: PC_BUILD; Uso: diseño")])
    change=capture_ticket_request(s,authenticated_customer_id=1)
    assert change["request_revision"] == 2 and "product_description" not in change["intake"]
    s.update(change,messages=[HumanMessage(content="Presupuesto: 2000")])
    prepared=capture_ticket_request(s,authenticated_customer_id=1)
    s.update(prepared,messages=[HumanMessage(content="Continuar")])
    assert capture_ticket_request(s,authenticated_customer_id=1)["pending_ticket_operation"] == prepared["pending_ticket_operation"]
    s["messages"]=[HumanMessage(content="Presupuesto: 3000")]
    with pytest.raises(RetryConflict):
        capture_ticket_request(s,authenticated_customer_id=1)


@pytest.mark.parametrize("text", ["¿Cuál es el horario?","¿Mi garantía sigue vigente?","Estado del ticket 1001","Hola"])
def test_informational(text):
    assert capture_ticket_request(state(text),authenticated_customer_id=1) is None


@pytest.mark.parametrize("text", ["No quiero comprar SSD","Quizás quiero reparar PC","Tal vez necesito instalar Windows"])
def test_ambiguous(text):
    assert "pending_ticket_operation" not in capture_ticket_request(state(text),authenticated_customer_id=1)


@pytest.mark.parametrize("value", ["0","-1","true","1.5"])
def test_invalid_quantity(value):
    assert "pending_ticket_operation" not in capture_ticket_request(state("Solicitud: SALE; Producto: SSD; Cantidad: "+value),authenticated_customer_id=1)


def test_identity_refund_and_insufficient():
    s=state("Quiero reparar")
    assert "pending_ticket_operation" not in capture_ticket_request(s,authenticated_customer_id=1)
    with pytest.raises(RetryConflict):
        capture_ticket_request(s,authenticated_customer_id=2)
    assert "pending_ticket_operation" not in capture_ticket_request(s,authenticated_customer_id=None)
    assert capture_ticket_request(state("Quiero un reembolso"),authenticated_customer_id=1)["intent"] == "REFUND"


@pytest.mark.parametrize("text,kind", [("Quiero comprar dos SSD de 500 GB","SALE"),("Mi laptop no enciende","REPAIR")])
def test_natural_preparation(text,kind):
    patch=capture_ticket_request(state(text),authenticated_customer_id=1)
    assert patch["pending_ticket_operation"]["payload"]["request_type"] == kind
    if kind == "SALE":
        assert patch["intake"]["quantity"] == 2
        assert patch["intake"]["product_description"] == "SSD de 500 GB"


def test_natural_missing_symptom_and_correction_lock():
    initial=capture_ticket_request(state("Necesito reparar mi computadora"),authenticated_customer_id=1)
    assert initial["intake"]["missing_fields"] == ["failure_description"]
    s=state("Quiero comprar dos SSD de 500 GB")
    s.update(capture_ticket_request(s,authenticated_customer_id=1))
    operation=s["pending_ticket_operation"]
    s["messages"]=[HumanMessage(content="Quiero tres en lugar de dos")]
    patch=capture_ticket_request(s,authenticated_customer_id=1)
    assert patch["ticket_correction_required"] is True
    s.update(patch,messages=[HumanMessage(content="Continuar")])
    assert capture_ticket_request(s,authenticated_customer_id=1)["ticket_correction_required"] is True
    assert s["pending_ticket_operation"] == operation


def test_quisiera_buy_not_technical_and_overheating():
    patch=capture_ticket_request(state("QUISIERA COMPRAR UNA SSD"),authenticated_customer_id=1)
    assert patch["intent"]=="SALE"
    assert patch["intake"]["quantity"]==1
    hardware=capture_ticket_request(state("Tengo una laptop Lenovo que se recalienta y demora en ejecutar aplicaciones"),authenticated_customer_id=1)
    assert hardware["intent"]=="REPAIR"
    assert "Lenovo" in hardware["intake"]["failure_description"]


def test_network_checkpoint_continuity_isolation_and_no_sql(network):
    module,_=network
    repo=MagicMock()
    saver=MemorySaver()
    graph=module.build_graph(checkpointer=saver,financial_repository=repo)
    config={"configurable":{"thread_id":"intake-one"}}
    ctx={"authenticated_customer_id":1}
    first=graph.invoke(state("Quiero comprar; Producto: SSD SATA 500GB"),config,context=ctx)
    assert "pending_ticket_operation" not in first
    result=graph.invoke(dict(messages=[HumanMessage(content="Cantidad: 2")],customer_id=1),config,context=ctx,durability="sync")
    operation=result["pending_ticket_operation"]
    assert result["current_agent"] == "soporte"
    rebuilt=module.build_graph(checkpointer=saver,financial_repository=repo)
    retry=rebuilt.invoke(dict(messages=[HumanMessage(content="Continuar")],customer_id=1),config,context=ctx)
    assert retry["pending_ticket_operation"] == operation
    other=rebuilt.invoke(state("Solicitud: SALE; Producto: SSD SATA 500GB; Cantidad: 1"),{"configurable":{"thread_id":"intake-two"}},context=ctx)
    assert other["pending_ticket_operation"]["payload"]["code"] != operation["payload"]["code"]
    assert repo.mock_calls == []


def test_saved_operation_survives_checkpoint_response_exception(network,monkeypatch):
    module,_=network
    saver=MemorySaver()
    original=saver.put
    persisted=[]
    def lost_response(config,checkpoint,metadata,new_versions):
        result=original(config,checkpoint,metadata,new_versions)
        pending=checkpoint.get("channel_values",{}).get("pending_ticket_operation")
        if pending and not persisted:
            persisted.append(pending)
            raise RuntimeError("Synthetic response loss after checkpoint")
        return result
    monkeypatch.setattr(saver,"put",lost_response)
    repo=MagicMock()
    graph=module.build_graph(checkpointer=saver,financial_repository=repo)
    config={"configurable":{"thread_id":"lost-intake-response"}}
    ctx={"authenticated_customer_id":1}
    with pytest.raises(RuntimeError):
        graph.invoke(state("Solicitud: SALE; Producto: SSD SATA 500GB; Cantidad: 1"),config,context=ctx,durability="sync")
    assert graph.get_state(config).values["pending_ticket_operation"] == persisted[0]
    recovered=module.build_graph(checkpointer=saver,financial_repository=repo).invoke(
        dict(messages=[HumanMessage(content="Continuar")],customer_id=1),config,context=ctx,durability="sync")
    assert recovered["pending_ticket_operation"] == persisted[0]
    assert repo.mock_calls == []


def test_faq_then_operation_and_other_customer_isolation(network):
    module,_=network
    repo=MagicMock()
    graph=module.build_graph(checkpointer=MemorySaver(),financial_repository=repo)
    one={"configurable":{"thread_id":"faq-to-action"}}
    faq=graph.invoke(state("¿Cuál es el horario?"),one,context={"authenticated_customer_id":1})
    assert "pending_ticket_operation" not in faq
    action=graph.invoke(dict(messages=[HumanMessage(content="Solicitud: SALE; Producto: SSD SATA 500GB; Cantidad: 1")],customer_id=1),one,context={"authenticated_customer_id":1})
    assert action["pending_ticket_operation"]["payload"]["customer_id"] == 1
    two=graph.invoke(dict(messages=[HumanMessage(content="Solicitud: SALE; Producto: RAM; Cantidad: 2")],customer_id=2,request_revision=0),
        {"configurable":{"thread_id":"customer-two"}},context={"authenticated_customer_id":2})
    assert two["pending_ticket_operation"]["payload"]["customer_id"] == 2
    assert graph.get_state(one).values["pending_ticket_operation"] == action["pending_ticket_operation"]
    assert repo.mock_calls == []
