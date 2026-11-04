"""TA-013: diagnostico preliminar y solicitudes de garantia sin servicios externos."""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool


@pytest.fixture
def hardware(monkeypatch):
    model = Mock()
    model.invoke.return_value = AIMessage(content="Orientacion preliminar")
    model.bind_tools.return_value = model
    monkeypatch.setattr("app.config.create_chat_model", lambda: model)

    @tool
    def consultar_base_conocimiento(consulta: str) -> str:
        """Consulta simulada sin red."""
        return "Resultado simulado"

    rag = ModuleType("app.rag.tools")
    rag.consultar_base_conocimiento = consultar_base_conocimiento
    monkeypatch.setitem(sys.modules, "app.rag.tools", rag)
    path = Path(__file__).resolve().parents[3] / "app/agents/decentralized/agents/hardware.py"
    spec = importlib.util.spec_from_file_location("isolated_ta013_hardware", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, model


def test_hardware_asks_device_type_before_assessing_physical_symptom(hardware):
    module, model = hardware
    result = module.hardware_node({"messages": [HumanMessage(content="Mi equipo no enciende")]})
    assert result["current_agent"] == "tecnico"
    assert "laptop" in result["messages"][0].content
    assert "no puedo confirmar la causa" in result["messages"][0].content.lower()
    model.invoke.assert_not_called()


@pytest.mark.parametrize("equipment", ["laptop", "computadora de escritorio"])
def test_hardware_uses_reported_device_without_reasking(hardware, equipment):
    module, model = hardware
    result = module.hardware_node({"messages": [HumanMessage(content="Mi equipo no enciende")],
                                   "intake": {"equipment": equipment}})
    assert result["messages"][0].content == "Orientacion preliminar"
    model.invoke.assert_called_once()


@pytest.mark.parametrize("reason", ["Solicito reparacion del equipo", "Solicito reemplazo del equipo"])
def test_warranty_request_stays_pending_review_without_chat_write(reason):
    from app.agents.decentralized.agents.warranty import warranty_node

    repository = Mock()
    repository.get_warranty.return_value = {
        "id": 10, "warranty_code": "WAR-TEST", "status": "ACTIVE",
        "effective_status": "ACTIVE", "start_date": "2026-01-01", "end_date": "2026-12-31",
        "warranty_months": 12, "item_or_service_name": "Equipo de prueba",
    }
    repository.get_ticket.return_value = {"request_type": "WARRANTY_CLAIM", "status": "NEW",
                                           "failure_description": reason}
    state = {"customer_id": 1, "ticket_id": 2, "request_revision": 0,
             "intent": "WARRANTY_CLAIM", "intake": {"warranty_code": "WAR-TEST"},
             "messages": [HumanMessage(content=reason)]}
    result = warranty_node(state, repository=repository, authenticated_customer_id=1)
    assert result["warranty_preparation_ready"] is True
    assert result["pending_warranty_operation"]["payload"]["reason"] == reason
    assert "no" in result["messages"][0].content.lower()
    repository.create_warranty_claim.assert_not_called()


def test_warranty_rejects_unverified_identity():
    from app.agents.decentralized.agents.warranty import warranty_node

    repository = Mock()
    result = warranty_node({"messages": []}, repository=repository)
    assert result["warranty_preparation_ready"] is False
    repository.get_warranty.assert_not_called()


@pytest.mark.parametrize("reason", ["Solicito reparacion del equipo", "Solicito reemplazo del equipo"])
def test_warranty_request_is_registered_for_review_only(reason, network, warranty_db):
    from langgraph.checkpoint.memory import MemorySaver

    module, _ = network
    repository = warranty_db[0]
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repository)
    config = {"configurable": {"thread_id": "ta013-" + reason.split()[1]}}
    context = {"authenticated_customer_id": 1}
    state = {"messages": [HumanMessage(content=reason)], "current_agent": "garantia",
             "customer_id": 1, "ticket_id": warranty_db[5]["id"], "request_revision": 0,
             "intent": "WARRANTY_CLAIM", "intake": {"warranty_code": "WAR-TEST"},
             "warranty_claim": {"reason": reason}}
    graph.invoke(state, config, context=context, durability="sync")
    pending = graph.get_state(config)
    assert pending.next == ("ejecutar_garantia",)
    assert pending.values["pending_warranty_operation"]["payload"]["reason"] == reason
    repository.create_warranty_claim = Mock(wraps=repository.create_warranty_claim)
    repository.create_warranty_claim.assert_not_called()

    result = graph.invoke(None, config, context=context, durability="sync")
    repository.create_warranty_claim.assert_called_once()
    claim = repository.get_warranty_claim(customer_id=1, claim_id=result["warranty_claim_id"])
    assert claim["reason"] == reason
    assert claim["status"] == "IN_REVIEW"
    assert repository.get_ticket(customer_id=1, ticket_id=state["ticket_id"])["status"] == "WARRANTY_IN_REVIEW"
    assert repository.get_logistics_context(customer_id=1, ticket_id=state["ticket_id"])["id"] == state["ticket_id"]
    assert result["current_agent"] == "logistica"


# Reutiliza fixtures aisladas: SQLite local y modelo/RAG simulados.
from tests.decentralized_reference.test_software_e2e import network
from tests.decentralized_reference.test_garantia import warranty_db
from tests.decentralized_reference.test_decentralized_repository import database
