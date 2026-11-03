from langchain_core.messages import HumanMessage

from app.agents.decentralized.graph import HANDOFF_TOOLS, auditar_soporte, route_entry
from app.agents.decentralized.soporte import soporte_node


def test_decentralized_refund_intent_hands_off_to_pending_request_handler():
    state = {
        "messages": [HumanMessage(content="Quiero solicitar un reembolso")],
        "turn_start_index": 0,
        "handoff_count": 0,
        "handoff_history": [],
        "tool_iterations": {},
        "errors": [],
    }

    proposed = soporte_node(state)
    tool_call = proposed["messages"][0].tool_calls[0]
    assert tool_call["name"] == "transferir_a_reembolsos"
    assert HANDOFF_TOOLS[tool_call["name"]] == "reembolsos"

    from langchain_core.messages import ToolMessage
    state["messages"].extend([
        proposed["messages"][0],
        ToolMessage(content="TRANSFERIR_REEMBOLSOS", tool_call_id=tool_call["id"], name=tool_call["name"]),
    ])
    audit = auditar_soporte(state)
    assert audit["next_agent"] == "reembolsos"
    assert route_entry({"current_agent": "reembolsos"}) == "soporte"
