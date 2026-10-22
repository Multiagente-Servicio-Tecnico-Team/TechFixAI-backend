import importlib
import importlib.util
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


def agent():
    return importlib.import_module("app.agents.decentralized.almacen")


def test_initial_imports_and_original_identity(network):
    module = agent()
    from app.agents.decentralized.almacen import warehouse_llm, almacen_llm
    assert warehouse_llm is almacen_llm is module._INITIAL_WAREHOUSE_LLM is module._resolve_warehouse_llm()


def test_single_initialization_and_binding_with_original_registry(network, monkeypatch):
    groq = sys.modules["langchain_groq"]
    original = groq.ChatGroq
    created, bindings = [], []
    class CountingGroq(original):
        def __init__(self, **kwargs):
            created.append(self)
            super().__init__(**kwargs)
        def bind_tools(self, tools, **kwargs):
            bound = super().bind_tools(tools, **kwargs)
            bindings.append((tools, kwargs, bound))
            return bound
    monkeypatch.setattr(groq, "ChatGroq", CountingGroq)
    path = Path(__file__).resolve().parents[1] / "app/agents/decentralized/warehouse.py"
    spec = importlib.util.spec_from_file_location("isolated_warehouse_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(created) == len(bindings) == 1
    assert module.llm is created[0]
    assert bindings[0][0] is module.warehouse_tools is module.almacen_tools
    assert bindings[0][1] == {}
    assert bindings[0][2] is module.warehouse_llm is module.almacen_llm
    for _ in range(2):
        module.warehouse_node({"messages": [HumanMessage(content="Consulta general")]})
    assert len(created) == len(bindings) == 1


@pytest.mark.parametrize("names", [("warehouse_llm",), ("almacen_llm",), ("warehouse_llm", "almacen_llm")])
@pytest.mark.parametrize("tool_response", [False, True])
def test_reassignment_invokes_selected_model_with_unchanged_messages_and_restores(network, monkeypatch, names, tool_response):
    module = agent()
    original = module.warehouse_llm
    response = (AIMessage(content="", tool_calls=[dict(name="transfer_to_sales", args={"reason": "Evaluar"}, id="tool")])
                if tool_response else AIMessage(content="Respuesta controlada"))
    replacement = MagicMock()
    replacement.invoke.return_value = response
    history = [HumanMessage(content="Consulta general", id="human")]
    before = deepcopy(history)
    with monkeypatch.context() as patch:
        for name in names:
            patch.setattr(module, name, replacement)
        assert module._resolve_warehouse_llm() is replacement
        result = module.warehouse_node({"messages": history})
        assert result == {"current_agent": "almacen", "messages": [response]}
        assert result["messages"][0] is response
        replacement.invoke.assert_called_once()
        arguments, kwargs = replacement.invoke.call_args
        assert kwargs == {} and len(arguments) == 1
        assert arguments[0][0] == SystemMessage(content=module.SYSTEM_PROMPT)
        assert arguments[0][1:] == module.build_warehouse_context({"messages": history})
        assert arguments[0][1] is history[0] and history == before
    assert module._resolve_warehouse_llm() is original


def test_conflicts_fail_closed_without_comparing_or_invoking_models(network, monkeypatch):
    module = agent()
    class IdentityOnlyModel:
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve models")
        def invoke(self, messages):
            raise AssertionError("Conflicting model must not run")
    monkeypatch.setattr(module, "warehouse_llm", IdentityOnlyModel())
    monkeypatch.setattr(module, "almacen_llm", IdentityOnlyModel())
    with pytest.raises(ValueError, match="Conflicting warehouse models"):
        module._resolve_warehouse_llm()
    result = module.warehouse_node({"messages": [HumanMessage(content="Consulta general")]})
    assert result["errors"] == ["Error en el agente Almacén: ValueError"]
    assert not result["messages"][0].tool_calls


def test_model_changes_between_invocations_and_direct_import_is_not_resynchronized(network, monkeypatch):
    module = agent()
    from app.agents.decentralized.almacen import almacen_llm as captured
    for name in ("warehouse_llm", "almacen_llm"):
        with monkeypatch.context() as patch:
            first, second = MagicMock(), MagicMock()
            first.invoke.return_value = AIMessage(content="Primera")
            second.invoke.return_value = AIMessage(content="Segunda")
            for model in (first, second):
                patch.setattr(module, name, model)
                result = module.warehouse_node({"messages": [HumanMessage(content="Consulta general")]})
                assert result["messages"][0] is model.invoke.return_value
            assert captured is module._INITIAL_WAREHOUSE_LLM
    assert module._resolve_warehouse_llm() is captured


@pytest.mark.parametrize("name", ["warehouse_llm", "almacen_llm"])
def test_selected_model_errors_keep_existing_safe_response(network, monkeypatch, name):
    module = agent()
    model = MagicMock()
    model.invoke.side_effect = RuntimeError("private detail")
    monkeypatch.setattr(module, name, model)
    result = module.warehouse_node({"messages": [HumanMessage(content="Consulta general")], "errors": ["previous"]})
    model.invoke.assert_called_once()
    assert result["errors"] == ["previous", "Error en el agente Almacén: RuntimeError"]
    assert "private detail" not in str(result)


@pytest.mark.parametrize("name", ["warehouse_llm", "almacen_llm"])
def test_checkpoint_resumes_with_current_model_without_preparing_turn(network, monkeypatch, name):
    graph_module, _ = network
    module = agent()
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "warehouse-model"}}
    graph = graph_module.build_graph(checkpointer=saver)
    graph.update_state(config, {"messages": [HumanMessage(content="Consulta general", id="human")],
        "current_agent": "almacen", "handoff_count": 0, "handoff_history": [], "handoff_records": [],
        "request_revision": 2}, as_node="preparar_turno")
    replacement = MagicMock()
    replacement.invoke.return_value = AIMessage(content="Orientacion controlada", id="response")
    monkeypatch.setattr(module, name, replacement)
    def forbidden(state):
        raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(graph_module, "prepare_turn", forbidden)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config)
    replacement.invoke.assert_called_once()
    assert result["messages"][-1].content == "Orientacion controlada"
    assert result["messages"][-1].id == "response"
    assert result["handoff_history"] == [] and result["handoff_count"] == 0
    assert graph.get_state(config).next == ()


@pytest.mark.parametrize("name,tool_name", [("warehouse_llm", "check_inventory"), ("almacen_llm", "consultar_inventario")])
@pytest.mark.parametrize("stock,destination", [(0, "compras"), (1, "compras"), (3, "ventas")])
def test_inventory_resume_keeps_stock_validation_and_existing_handoffs(network, monkeypatch, name, tool_name, stock, destination):
    graph_module, controls = network
    controls["inventory_stock"] = stock
    forbidden = MagicMock()
    forbidden.invoke.side_effect = AssertionError("Verified inventory must not use LLM")
    monkeypatch.setattr(agent(), name, forbidden)
    args = {"part_name": "SSD de prueba", "quantity": 2} if tool_name == "check_inventory" else {"nombre_repuesto": "SSD de prueba", "cantidad": 2}
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name, args=args, id="inventory-call")])
    before = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "warehouse-inventory-model"}}
    graph = graph_module.build_graph(checkpointer=saver)
    graph.update_state(config, {"messages": [HumanMessage(content="SSD de prueba", id="human"), event],
        "current_agent": "almacen", "required_parts": [{"name": "SSD de prueba", "quantity": 2}],
        "inventory_revision": 2, "request_revision": 2, "inventory_pending": True,
        "inventory_requested_by": "ventas", "handoff_history": [], "handoff_count": 0,
        "handoff_records": []}, as_node="almacen")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_almacen"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "inventory-call")]
    assert outputs[0].status != "error" and event == before
    assert controls["inventory_calls"] == [("SSD de prueba", 2)]
    assert result["inventory_pending"] is False and result["inventory_revision"] == 2
    assert result["inventory_results"][0]["stock"] == stock
    assert result["inventory_results"][0]["available"] is (stock >= 2)
    assert result["handoff_history"] == [{"origin": "almacen", "destination": destination}]
    assert result["handoff_count"] == 1
    forbidden.invoke.assert_not_called()
    assert not result.get("payment_id") and not result.get("quote_id")


@pytest.mark.parametrize("name", ["warehouse_llm", "almacen_llm"])
def test_inventory_error_guard_precedes_model_resolution(network, monkeypatch, name):
    module = agent()
    replacement = MagicMock()
    monkeypatch.setattr(module, name, replacement)
    result = module.warehouse_node({"messages": [HumanMessage(content="Consulta general")],
        "required_parts": [{"name": "SSD de prueba", "quantity": 1}], "errors": ["Error inventario"]})
    replacement.invoke.assert_not_called()
    assert result["current_agent"] == "almacen"
    assert not result["messages"][0].tool_calls


