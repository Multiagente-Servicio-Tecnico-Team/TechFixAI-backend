"""Production graph with simulated dependencies; no app.demo or commercial writes."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network, pairs, call
from app.agents.decentralized.ticket_intake import capture_ticket_request
from app.agents.decentralized.policy import triaje_soporte
from app.agents.decentralized.garantia import garantia_node
from app.database.decentralized_repository import RetryConflict


def initial(text, **extra):
    return dict(messages=[HumanMessage(content=text)], customer_id=1, request_revision=0, **extra)


def test_natural_generic_purchase_collects_specs_before_preparation():
    state = initial("Quisiera comprar una SSD")
    patch = capture_ticket_request(state, authenticated_customer_id=1)
    assert patch["intent"] == "SALE" and patch["intake"]["quantity"] == 1
    assert "pending_ticket_operation" not in patch
    assert "capacidad e interfaz" in patch["messages"][0].content
    state.update(patch, messages=[HumanMessage(content="500 GB SATA")])
    ready = capture_ticket_request(state, authenticated_customer_id=1)
    assert ready["pending_ticket_operation"]["payload"]["request_type"] == "SALE"
    assert ready["intake"]["product_description"] == "SSD 500 GB SATA"
    assert "ticket_id" not in ready


def test_plain_quantity_answer_preserves_product():
    state = initial("Quiero comprar; Producto: SSD SATA 500GB")
    state.update(capture_ticket_request(state, authenticated_customer_id=1),
                 messages=[HumanMessage(content="dos")])
    result = capture_ticket_request(state, authenticated_customer_id=1)
    assert result["intake"]["quantity"] == 2
    assert result["intake"]["product_description"] == "SSD SATA 500GB"


@pytest.mark.parametrize("text,expected", [
    ("Mi laptop Lenovo se recalienta y funciona lentamente", "tecnico"),
    ("Mi laptop no se recalienta; la aplicación falla", "software"),
    ("Quizás se recalienta", None),
])
def test_temperature_is_reported_evidence_not_diagnosis(text, expected):
    assert triaje_soporte(initial(text)) == expected


@pytest.mark.parametrize("text,target", [
    ("Mi laptop Lenovo se recalienta y funciona lentamente", "tecnico"),
    ("La aplicación se cierra", "software"),
])
def test_authenticated_existing_ticket_reaches_specialist(network, text, target):
    module, controls = network
    controls["handlers"][target] = lambda messages: AIMessage(content="Orientación preliminar de prueba")
    repo = MagicMock()
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    result = graph.invoke(initial(text, ticket_id=10),
        {"configurable": {"thread_id": target}}, context={"authenticated_customer_id": 1})
    assert result["current_agent"] == target
    assert result["handoff_history"] == [{"origin": "soporte", "destination": target}]
    assert result["ticket_id"] == 10
    assert not result.get("pending_ticket_operation")
    assert repo.mock_calls == []
    pairs(result)


def test_natural_warranty_query_uses_authenticated_repository(network):
    module, _ = network
    repo = MagicMock()
    repo.get_warranty.return_value = dict(id=2, warranty_code="WAR-TEST", status="ACTIVE",
        effective_status="ACTIVE", start_date=date.today(), end_date=date.today()+timedelta(days=20),
        warranty_months=3, item_or_service_name="Fixture")
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    config = {"configurable": {"thread_id": "natural-warranty"}}
    first = graph.invoke(initial("¿Mi garantía sigue vigente?"), config,
                         context={"authenticated_customer_id": 1})
    assert first["current_agent"] == "garantia"
    result = graph.invoke({"messages": [HumanMessage(content="Mi código es WAR-TEST")], "customer_id": 1},
                         config, context={"authenticated_customer_id": 1})
    repo.get_warranty.assert_called_once_with(customer_id=1, warranty_code="WAR-TEST")
    assert result["warranty_code"] == "WAR-TEST" and not result.get("ticket_id")
    repo.create_warranty_claim.assert_not_called()
    pairs(result)


def test_warranty_change_cannot_replace_prepared_claim():
    repo = MagicMock()
    with pytest.raises(RetryConflict):
        garantia_node(initial("Mi código es WAR-OTHER", warranty_code="WAR-TEST",
            pending_warranty_operation={"synthetic": True}), repository=repo, authenticated_customer_id=1)
    assert repo.mock_calls == []


@pytest.mark.parametrize("foreign", [False, True])
def test_ticket_lookup_uses_server_identity_and_real_repository(network, foreign):
    import json
    from langchain_core.messages import ToolMessage
    module, controls = network
    repo = MagicMock()
    if foreign:
        repo.get_ticket.side_effect = LookupError("Private customer details must not appear")
    else:
        repo.get_ticket.return_value = {"id": 1001, "code": "TCK-FIXTURE", "status": "NEW"}
    controls["handlers"]["soporte"] = lambda messages: (
        AIMessage(content="Consulta terminada") if isinstance(messages[-1], ToolMessage)
        else call("consultar_estado_ticket", numero_ticket=1001))
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    result = graph.invoke(initial("Estado del ticket 1001"),
        {"configurable": {"thread_id": "ticket-"+str(foreign)}}, context={"authenticated_customer_id": 1})
    repo.get_ticket.assert_called_once_with(customer_id=1, ticket_id=1001)
    output = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    data = json.loads(output.content)
    assert data["verified"] is not foreign
    assert "En revisión" not in output.content and "Private customer" not in output.content
    repo.create_ticket.assert_not_called()
    pairs(result)
