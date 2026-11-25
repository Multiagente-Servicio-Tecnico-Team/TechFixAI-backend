"""Reproducible six-flow demo: real graph, mocked model/RAG/SQL reads, no writes."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import json
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from app.agents.decentralized.data_compat import normalize_handoff_history_entry
from test_software_e2e import network, call, pairs


@pytest.fixture(autouse=True)
def isolated_traces():
    # Test-only isolation; does not change API tracing configuration or .env.
    from langsmith import tracing_context
    with tracing_context(enabled=False):
        yield


@pytest.mark.parametrize("flow,message", [
    ("reparacion","Mi laptop no enciende"),
    ("ensamblaje","Quiero armar una PC; Uso: programación; Presupuesto: 2500"),
    ("venta","Quiero comprar dos SSD de 500 GB"),
    ("reclamo","Quiero reclamar mi garantía; Código: WAR-DEMO; Motivo: se apaga"),
    ("vigencia","Código: WAR-DEMO"),
    ("faq","¿Qué servicios ofrecen?"),
])
def test_six_delivery_flows(network,flow,message):
    module,controls=network
    repo=MagicMock()
    repo.get_warranty.return_value=dict(id=1,warranty_code="WAR-DEMO",status="ACTIVE",effective_status="ACTIVE",
        start_date=date.today(),end_date=date.today()+timedelta(days=30),warranty_months=3,item_or_service_name="Artículo sintético de demostración")
    def support_model(messages):
        if flow == "vigencia":
            return call("transferir_a_garantia",motivo="Consultar vigencia sin crear ticket")
        if any(isinstance(m,ToolMessage) and m.name=="consultar_base_conocimiento" for m in messages):
            return AIMessage(content="Documento técnico de prueba; fuente: fixture. Esta respuesta no certifica el RAG productivo.")
        return call("consultar_base_conocimiento",consulta="Servicios documentados de prueba")
    controls["handlers"]["soporte"]=support_model
    graph=module.build_graph(checkpointer=MemorySaver(),financial_repository=repo)
    initial=dict(messages=[HumanMessage(content=message)],customer_id=1,request_revision=0)
    if flow == "vigencia":
        initial["intent"]="WARRANTY_STATUS_CHECK"
    result=graph.invoke(initial,{"configurable":{"thread_id":"delivery-"+flow}},context={"authenticated_customer_id":1},durability="sync")
    history=result.get("handoff_history",[])
    agents=["soporte"]+[normalize_handoff_history_entry(item)["destination"] for item in history]
    pending=result.get("pending_ticket_operation")
    if flow in {"reparacion","ensamblaje","venta","reclamo"}:
        assert pending and not history
        assert "ticket_id" not in result
        assert repo.mock_calls == []
    elif flow == "vigencia":
        repo.get_warranty.assert_called_once_with(customer_id=1,warranty_code="WAR-DEMO")
        assert agents==["soporte","garantia"] and not pending
    else:
        assert controls["rag_calls"] and not pending
        assert repo.mock_calls == []
    for method in ("create_ticket","create_accepted_quote","create_pending_payment","create_initial_logistics","create_warranty","create_warranty_claim"):
        getattr(repo,method).assert_not_called()
    assert len(module.AGENT_NODES)==9
    pairs(result)
    print(json.dumps(dict(flujo=flow,mensaje=message,agentes=agents,handoffs=history,
        resultado=result["messages"][-1].content,operacion="preparada; escritura de ticket no implementada" if pending else "lectura o RAG simulados",
        bloqueo="ticket persistido pendiente; no se ejecutan especialistas posteriores" if pending else None),ensure_ascii=False))


def test_exact_service_faq_ignores_old_repair_history(network):
    module,controls=network
    repo=MagicMock()
    graph=module.build_graph(checkpointer=MemorySaver(),financial_repository=repo)
    result=graph.invoke(dict(messages=[HumanMessage(content="Mi laptop no enciende"),
        AIMessage(content="¿Qué sistema operativo usas?"),HumanMessage(content="¿Qué servicios técnicos ofrecen?")],
        customer_id=1,request_revision=0),{"configurable":{"thread_id":"faq-regression"}},context={"authenticated_customer_id":1})
    assert result["current_agent"] == "soporte"
    assert not result.get("handoff_history") and not result.get("pending_ticket_operation")
    assert not result.get("ticket_id")
    assert controls["rag_calls"] == ["¿Qué servicios técnicos ofrecen?"]
    assert "fixture" in result["messages"][-1].content
    assert repo.mock_calls == []
