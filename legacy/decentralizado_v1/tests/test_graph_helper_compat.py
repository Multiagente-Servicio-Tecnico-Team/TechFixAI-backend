import ast
from copy import deepcopy
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized import policy
from test_software_e2e import network

ALIASES = [
    ("guardar_inventario", "record_inventory_results"),
    ("preparar_turno", "prepare_turn"),
    ("auditar_soporte", "audit_support"),
    ("auditar_tecnico", "audit_hardware"),
    ("auditar_ventas", "audit_sales"),
    ("auditar_almacen", "audit_warehouse"),
    ("auditar_software", "audit_software"),
    ("auditar_compras", "audit_purchasing"),
    ("auditar_facturacion", "audit_billing"),
    ("auditar_logistica", "audit_logistics"),
]
AUDITORS = list(zip(ALIASES[2:], ["soporte", "tecnico", "ventas", "almacen", "software", "compras", "facturacion", "logistica"]))


@pytest.mark.parametrize("legacy,canonical", ALIASES)
def test_legacy_imports_share_implementation_and_signature(network, legacy, canonical):
    module, _ = network
    assert getattr(module, legacy) is getattr(module, canonical)
    assert inspect.signature(getattr(module, legacy)) == inspect.signature(getattr(module, canonical))


@pytest.mark.parametrize("names,role", AUDITORS)
def test_auditors_return_identical_patches_without_mutating_input(network, names, role):
    module, _ = network
    state = dict(messages=[HumanMessage(content="Consulta")], tool_iterations={role: 1}, handoff_count=0)
    before = deepcopy(state)
    old, new = (getattr(module, name) for name in names)
    assert old(state) == new(state) == module.record_handoff(state, origin=role)
    assert old(state)["tool_iterations"][role] == 2 and state == before


def transfer_state():
    return dict(messages=[HumanMessage(content="Consulta"),
        AIMessage(content="", tool_calls=[dict(name="transfer_to_hardware", args={"reason":"Evaluar"}, id="call")]),
        ToolMessage(content="TRANSFERIR_TECNICO: Evaluar", name="transfer_to_hardware", tool_call_id="call")],
        request_revision=2, handoff_count=0, handoff_history=[], handoff_records=[])


@pytest.mark.parametrize("style", ["positional", "english", "legacy_keyword", "legacy_entry", "legacy_entry_keyword"])
def test_handoff_entry_points_preserve_results_and_history(network, style):
    module, _ = network
    state = transfer_state(); before = deepcopy(state)
    if style == "positional": result = module.record_handoff(state, "soporte")
    elif style == "english": result = module.record_handoff(state, origin="soporte")
    elif style == "legacy_keyword": result = module.record_handoff(state, origen="soporte")
    elif style == "legacy_entry": result = module.registrar_handoff(state, "soporte")
    else: result = module.registrar_handoff(state, origen="soporte")
    assert result == module.record_handoff(state, origin="soporte")
    assert result["handoff_history"] == [{"origin":"soporte", "destination":"tecnico"}]
    assert result["handoff_count"] == 1 and result["handoff_records"][0]["reason"] == "Evaluar"
    assert state == before


@pytest.mark.parametrize("arguments", [{}, {"origin":"soporte", "origen":"soporte"}, {"origin":"soporte", "origen":"ventas"}, {"origin":None, "origen":"soporte"}])
def test_missing_or_double_origin_is_rejected_without_mutation(network, arguments):
    module, _ = network
    state = transfer_state(); before = deepcopy(state)
    with pytest.raises(TypeError): module.record_handoff(state, **arguments)
    assert state == before


def test_turn_reset_preserves_business_and_pending_operation(network):
    module, _ = network
    messages = [HumanMessage(content="Anterior"), AIMessage(content="Respuesta"), HumanMessage(content="Continuar")]
    state = dict(messages=messages, ticket_id=3, customer_id=1, pending_payment_operation={"payload":{"payment_code":"PAY-TEST"}},
        handoff_count=4, handoff_history=[{"origin":"soporte", "destination":"ventas"}], handoff_records=[{"metadata":"historical"}],
        errors=["Previo"], tool_iterations={"ventas":5}, next_agent="ventas", ticket_preparation_ready=True)
    before = deepcopy(state)
    patch = module.prepare_turn(state)
    assert patch == module.preparar_turno(state) == dict(turn_start_index=2, ticket_preparation_ready=False,
        handoff_count=0, handoff_history=[], handoff_records=[], tool_iterations={}, errors=[], next_agent=None)
    merged = {**state, **patch}
    assert merged["ticket_id"] == 3 and merged["customer_id"] == 1
    assert merged["pending_payment_operation"] == state["pending_payment_operation"] and state == before


def test_inventory_alias_keeps_verified_results(network):
    module, _ = network
    state = dict(request_revision=2, inventory_revision=2, required_parts=[{"name":"SSD de prueba", "quantity":1}],
        messages=[ToolMessage(name="check_inventory",tool_call_id="lookup",content='{"requested_name":"SSD de prueba","name":"SSD de prueba","quantity":1,"stock":3,"available":true,"found":true,"unit_price":"180.00"}')])
    before = deepcopy(state)
    result = module.record_inventory_results(state)
    assert result == module.guardar_inventario(state)
    assert result["inventory_pending"] is False and result["inventory_revision"] == 2
    assert result["inventory_results"][0]["tool_call_id"] == "lookup" and state == before


def test_customer_service_constant_remains_identical_and_legacy_importable():
    assert policy.CUSTOMER_SERVICE_UNAVAILABLE is policy.ATENCION_NO_CONFIGURADA
    tree = ast.parse((Path(__file__).resolve().parents[1]/"app/agents/decentralized/policy.py").read_text(encoding="utf-8"))
    literal = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="CUSTOMER_SERVICE_UNAVAILABLE" for t in n.targets))
    assert literal == policy.ATENCION_NO_CONFIGURADA


@pytest.mark.parametrize("mode", ["plain", "financial", "tickets"])
def test_registered_nodes_routes_and_interrupt_names_are_preserved(network, mode):
    module, _ = network
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=None if mode=="plain" else MagicMock(), ticket_writes=mode=="tickets")
    view = graph.get_graph()
    expected = {"__start__", "__end__", "guardar_inventario", "preparar_turno"}
    expected |= set(module.AGENT_NODES) | {role+"_tools" for role in module.AGENT_NODES} | {"auditar_"+role for role in module.AGENT_NODES}
    expected |= {prefix+kind for prefix in ["preparar_", "ejecutar_"] for kind in ["pago", "logistica", "garantia"]}
    if mode=="tickets": expected |= {"preparar_ticket", "ejecutar_ticket"}
    assert set(view.nodes) == expected
    assert list(graph.interrupt_before_nodes) == ([] if mode=="plain" else ["ejecutar_pago", "ejecutar_logistica", "ejecutar_garantia"] + (["ejecutar_ticket"] if mode=="tickets" else []))
    edges = {(edge.source, edge.target) for edge in view.edges}
    assert ("__start__", "preparar_turno") in edges
    assert ("almacen_tools", "guardar_inventario") in edges and ("guardar_inventario", "auditar_almacen") in edges
    for role in module.AGENT_NODES:
        if role!="almacen": assert (role+"_tools", "auditar_"+role) in edges
    for kind in ["pago", "logistica", "garantia"] + (["ticket"] if mode=="tickets" else []):
        assert ("preparar_"+kind, "ejecutar_"+kind) in edges


def test_checkpoint_with_legacy_pending_auditor_resumes_without_turn_reset(network, monkeypatch):
    module, _ = network
    saver = MemorySaver(); config = {"configurable":{"thread_id":"legacy-auditor"}}
    state = {**transfer_state(), "current_agent":"soporte", "customer_id":1, "ticket_id":7}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config,state,as_node="soporte_tools")
    assert graph.get_state(config).next == ("auditar_soporte",)
    def forbidden(state): raise AssertionError("Preparation must not rerun")
    monkeypatch.setattr(module,"prepare_turn",forbidden)
    result = module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_soporte"])
    assert result["handoff_history"] == [{"origin":"soporte", "destination":"tecnico"}]
    assert result["handoff_count"] == 1 and result["customer_id"] == 1 and result["ticket_id"] == 7
