"""Imports compatibles y topologia capturada antes de reorganizar."""
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from langgraph.checkpoint.memory import MemorySaver
from .test_software_e2e import network

PATHS = {'support': 'agents/support', 'hardware': 'agents/hardware', 'sales': 'agents/sales', 'warehouse': 'agents/warehouse', 'software': 'agents/software', 'purchasing': 'agents/purchasing', 'billing': 'agents/billing', 'logistics': 'agents/logistics', 'warranty': 'agents/warranty', 'graph': 'workflow/graph', 'state': 'workflow/state', 'handoffs': 'workflow/handoffs', 'conversation': 'workflow/conversation', 'policy': 'policies/policy', 'data_compat': 'compatibility/data_compat', 'ticket_intake': 'operations/ticket_intake', 'ticket_operations': 'operations/ticket_operations', 'quote_operations': 'operations/quote_operations', 'payment_operations': 'operations/payment_operations', 'logistics_operations': 'operations/logistics_operations', 'warranty_operations': 'operations/warranty_operations', 'soporte': 'agents/support', 'tecnico': 'agents/hardware', 'almacen': 'agents/warehouse', 'compras': 'agents/purchasing', 'facturacion': 'agents/billing', 'logistica': 'agents/logistics', 'garantia': 'agents/warranty'}


def test_leader_sales_path_is_preserved_beside_the_adapted_sales_role(network, monkeypatch):
    monkeypatch.delitem(sys.modules, "app.agents.decentralized.ventas", raising=False)
    leader = importlib.import_module("app.agents.decentralized.ventas")
    adapted = importlib.import_module("app.agents.decentralized.agents.sales")
    assert leader is not adapted
    assert callable(leader.ventas_node)
    assert callable(adapted.sales_node)

@pytest.mark.parametrize("old,new", PATHS.items())
def test_public_paths_share_the_same_module(network, monkeypatch, old, new):
    implementation = importlib.import_module("app.agents.decentralized." + new.replace("/", "."))
    # Ejecutar el shim real, no reutilizar el alias instalado por la fixture.
    public_name = "app.agents.decentralized." + old
    monkeypatch.delitem(sys.modules, public_name, raising=False)
    public = importlib.import_module(public_name)
    assert public is implementation
    for symbol, value in vars(implementation).items():
        if not symbol.startswith("__"):
            assert getattr(public, symbol) is value

@pytest.mark.parametrize("ticket,quote", [(False,False),(True,False),(False,True),(True,True)])
def test_roles_routes_nodes_and_write_options_match_the_previous_graph(network,ticket,quote):
    module,_=network
    assert set(module.AGENT_NODES) == {"soporte","tecnico","ventas","almacen","software","compras","facturacion","logistica","garantia"}
    graph=module.build_graph(checkpointer=MemorySaver(),financial_repository=MagicMock(),ticket_writes=ticket,quote_writes=quote)
    diagram=graph.get_graph()
    actual={"nodes":sorted(diagram.nodes),"edges":sorted([e.source,e.target,e.conditional] for e in diagram.edges),"interrupt_before":sorted(graph.interrupt_before_nodes)}
    expected=json.loads(Path(__file__).with_name("decentralized_topology.json").read_text(encoding="utf-8"))
    if quote:
        assert "ventas_directa_tools" in actual["nodes"]
        assert ["ventas", "ventas_directa_tools", True] in actual["edges"]
        assert ["ventas_directa_tools", "auditar_ventas", False] in actual["edges"]
        actual["nodes"].remove("ventas_directa_tools")
        actual["edges"].remove(["ventas", "ventas_directa_tools", True])
        actual["edges"].remove(["ventas_directa_tools", "auditar_ventas", False])
    assert actual == expected[f"{int(ticket)}{int(quote)}"]
