"""Compras consultivo determinista: declara las capacidades disponibles."""
from langchain_core.messages import AIMessage, ToolMessage
from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import evaluate_supply, handoff
from app.agents.decentralized.tools.compras_tools import get_sourcing_capabilities
from app.agents.decentralized.tools.purchasing_handoff_tools import transfer_to_sales
from app.agents.procurement import procurement_node as shared_procurement_node

purchasing_tools = [get_sourcing_capabilities, transfer_to_sales]
compras_tools = purchasing_tools


def purchasing_node(state: AgentState):
    """Keep unsupported customer procurement behavior identical across graphs."""
    return shared_procurement_node(state)


compras_node = purchasing_node
