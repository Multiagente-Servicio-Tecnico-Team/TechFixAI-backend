import ast
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import ValidationError

from app.agents.decentralized.tools.soporte_tools import (
    authenticated_ticket_status_tool, authenticated_ticket_tool,
    consultar_estado_ticket, get_ticket_status,
)
from test_software_e2e import network


VARIANTS = [("get_ticket_status", "ticket_id"), ("consultar_estado_ticket", "numero_ticket")]
ROOT = Path(__file__).resolve().parents[1]


class LookupState(MessagesState):
    customer_id: int


def repository():
    repo = MagicMock()
    repo.get_ticket.return_value = {"id": 1001, "code": "TCK-SYNTHETIC", "status": "NEW"}
    return repo


def tools(repo):
    return [authenticated_ticket_status_tool(repo), authenticated_ticket_tool(repo)]


def event(name, parameter, identifier="lookup", **extra):
    return AIMessage(content="", tool_calls=[dict(name=name, args={parameter: 1001, **extra}, id=identifier)], id="request")


def execute(repo, message, context=None):
    builder = StateGraph(LookupState, context_schema=dict)
    builder.add_node("tools", ToolNode(tools(repo), handle_tool_errors=True))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    return builder.compile().invoke({"messages": [message], "customer_id": 999}, context=context)


def output(result):
    messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(messages) == 1
    return messages[0], json.loads(messages[0].content)


@pytest.mark.parametrize("authenticated", [False, True])
@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_public_schema_is_exact_and_injected_identity_is_hidden(authenticated, name, parameter):
    tool = next(item for item in tools(repository()) if item.name == name) if authenticated else (
        get_ticket_status if name == "get_ticket_status" else consultar_estado_ticket)
    schema = tool.tool_call_schema.model_json_schema()
    assert tool.name == name
    assert set(schema["properties"]) == {parameter}
    assert schema["properties"][parameter]["type"] == "integer"
    assert schema["required"] == [parameter]
    assert "runtime" not in schema["properties"] and "authenticated_customer_id" not in schema["properties"]
    assert ("runtime" in tool.args_schema.model_fields) is authenticated


@pytest.mark.parametrize("ticket_id", [1001, 1002, 1003, 9999])
def test_simulated_variants_preserve_text_results(ticket_id):
    assert get_ticket_status.invoke({"ticket_id": ticket_id}) == consultar_estado_ticket.invoke({"numero_ticket": ticket_id})


@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_simulated_variant_requires_its_own_public_argument(name, parameter):
    tool = get_ticket_status if name == "get_ticket_status" else consultar_estado_ticket
    with pytest.raises(ValidationError):
        tool.invoke({})
    with pytest.raises(ValidationError):
        tool.invoke({"numero_ticket" if parameter == "ticket_id" else "ticket_id": 1001})


@pytest.mark.parametrize("name,parameter", VARIANTS)
@pytest.mark.parametrize("identity", [None, 0, -1, True, "1", 1.0])
def test_missing_or_invalid_identity_never_queries_or_falls_back(name, parameter, identity):
    repo = repository()
    message, data = output(execute(repo, event(name, parameter), {"authenticated_customer_id": identity}))
    assert data == {"verified": False, "detail": "Se requiere una sesión autenticada."}
    assert message.tool_call_id == "lookup" and message.name == name
    assert repo.mock_calls == []


@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_absent_context_cannot_be_replaced_by_state_or_model_arguments(name, parameter):
    repo = repository()
    request = event(name, parameter, customer_id=1, authenticated_customer_id=1,
                    runtime={"context": {"authenticated_customer_id": 1}})
    before = deepcopy(request)
    _, data = output(execute(repo, request))
    assert data["verified"] is False
    assert repo.mock_calls == [] and request == before


@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_context_overrides_forged_runtime_and_arguments(name, parameter):
    repo = repository()
    request = event(name, parameter, customer_id=999, authenticated_customer_id=999,
                    runtime={"context": {"authenticated_customer_id": 999}})
    before = deepcopy(request)
    message, data = output(execute(repo, request, {"authenticated_customer_id": 1}))
    assert data == {"verified": True, "ticket_id": 1001, "ticket_code": "TCK-SYNTHETIC", "status": "NEW"}
    repo.get_ticket.assert_called_once_with(customer_id=1, ticket_id=1001)
    assert len(repo.mock_calls) == 1
    assert request == before and message.tool_call_id == "lookup"


@pytest.mark.parametrize("name,parameter", VARIANTS)
@pytest.mark.parametrize("error", [LookupError("foreign private account"), LookupError("missing private ticket"), RuntimeError("private storage details")])
def test_foreign_missing_and_storage_errors_never_expose_details_or_simulation(name, parameter, error):
    repo = repository()
    repo.get_ticket.side_effect = error
    message, data = output(execute(repo, event(name, parameter), {"authenticated_customer_id": 1}))
    assert data["verified"] is False and set(data) == {"verified", "detail"}
    assert "private" not in message.content and "En revisión" not in message.content
    assert data["detail"] == ("No se encontró un ticket autorizado." if isinstance(error, LookupError)
                               else "No fue posible verificar el ticket en el almacenamiento.")
    repo.get_ticket.assert_called_once_with(customer_id=1, ticket_id=1001)
    assert len(repo.mock_calls) == 1


def test_registry_and_prompt_expose_only_english_to_model(network):
    module, _ = network
    names = [item.name for item in module.soporte_tools]
    assert names.count("get_ticket_status") == 1 and "consultar_estado_ticket" not in names
    source = (ROOT / "app/agents/decentralized/support.py").read_text(encoding="utf-8")
    prompt = next(ast.literal_eval(node.value) for node in ast.parse(source).body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in node.targets))
    assert "get_ticket_status" in prompt and "consultar_estado_ticket" not in prompt
    from app.agents.decentralized.tools.support_handoff_tools import legacy_handoff_tools
    expected = set(names) | {"consultar_estado_ticket"} | {tool.name for tool in legacy_handoff_tools}
    simulated = module.build_graph().get_graph().nodes["soporte_tools"].data.tools_by_name
    assert set(simulated) == expected
    for name in dict(VARIANTS):
        assert "runtime" not in simulated[name].args_schema.model_fields
    real = module.build_graph(checkpointer=MemorySaver(), financial_repository=repository()).get_graph().nodes["soporte_tools"].data.tools_by_name
    assert set(real) == expected
    for name, parameter in VARIANTS:
        assert "runtime" in real[name].args_schema.model_fields
        assert set(real[name].tool_call_schema.model_json_schema()["properties"]) == {parameter}


@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_authenticated_graph_replaces_any_simulated_registered_variant(network, monkeypatch, name, parameter):
    module, controls = network
    monkeypatch.setattr(module, "soporte_tools", [*module.soporte_tools, consultar_estado_ticket])
    repo = repository()
    repo.get_ticket.side_effect = LookupError("private")
    controls["handlers"]["soporte"] = lambda messages: (
        AIMessage(content="Fin") if isinstance(messages[-1], ToolMessage) else event(name, parameter))
    result = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo).invoke(
        dict(messages=[HumanMessage(content="Estado del ticket 1001")], customer_id=1),
        {"configurable": {"thread_id": "replace-simulation"}}, context={"authenticated_customer_id": 1})
    _, data = output(result)
    assert data["verified"] is False
    repo.get_ticket.assert_called_once_with(customer_id=1, ticket_id=1001)
    assert len(repo.mock_calls) == 1


@pytest.mark.parametrize("style", ["english", "legacy", "batch"])
@pytest.mark.parametrize("resume", [False, True])
def test_real_graph_calls_resume_and_message_correspondence(network, style, resume):
    module, controls = network
    variants = [dict(name=name, args={parameter: 1001}, id=f"lookup-{i}") for i, (name, parameter) in enumerate(VARIANTS)]
    calls = variants if style == "batch" else [variants[style == "legacy"]]
    request = AIMessage(content="", tool_calls=calls, id="lookup-event")
    before = deepcopy(request)
    controls["handlers"]["soporte"] = lambda messages: (
        AIMessage(content="Fin") if isinstance(messages[-1], ToolMessage) else request)
    repo = repository()
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "ticket-status-compat"}}
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    if resume:
        graph.update_state(config, dict(messages=[HumanMessage(content="Estado del ticket 1001", id="user"), request],
            customer_id=999, current_agent="soporte", handoff_history=[]), as_node="soporte")
        graph = module.build_graph(checkpointer=saver, financial_repository=repo)
        result = graph.invoke(None, config, context={"authenticated_customer_id": 1})
    else:
        result = graph.invoke(dict(messages=[HumanMessage(content="Estado del ticket 1001")], customer_id=1),
                              config, context={"authenticated_customer_id": 1})
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(json.loads(message.content) == dict(verified=True, ticket_id=1001, ticket_code="TCK-SYNTHETIC", status="NEW") for message in outputs)
    assert repo.get_ticket.call_count == len(calls) and len(repo.mock_calls) == len(calls)
    assert all(call.kwargs == dict(customer_id=1, ticket_id=1001) for call in repo.get_ticket.call_args_list)
    assert request == before and result["handoff_history"] == []


@pytest.mark.parametrize("name,parameter", VARIANTS)
def test_resumed_checkpoint_reauthorizes_with_current_context(network, name, parameter):
    module, _ = network
    repo = repository()
    repo.get_ticket.side_effect = LookupError("private owner")
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "ticket-owner-check"}}
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    graph.update_state(config, dict(messages=[HumanMessage(content="Estado del ticket 1001", id="user"), event(name, parameter)],
        current_agent="soporte", customer_id=1), as_node="soporte")
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    result = graph.invoke(None, config, context={"authenticated_customer_id": 2})
    _, data = output(result)
    assert data["verified"] is False
    repo.get_ticket.assert_called_once_with(customer_id=2, ticket_id=1001)
    assert len(repo.mock_calls) == 1
