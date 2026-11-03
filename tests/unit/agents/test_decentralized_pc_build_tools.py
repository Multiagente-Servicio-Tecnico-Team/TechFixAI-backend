"""The original network does not silently add profiles or select components."""
from langchain_core.messages import HumanMessage
from app.agents.decentralized.policy import build_verified_quote
from app.agents.decentralized.handoffs import HANDOFF_TOOLS


def test_pc_build_keeps_original_incomplete_quote_without_verified_components():
    quote, reply = build_verified_quote([dict(name="SSD", quantity=1, stock=2,
        unit_price="80.00", available=True, found=True)], [], request_type="PC_BUILD")
    assert quote["total"] is None and quote["status"] == "incomplete"
    assert "compatibilidad" in reply


def test_support_hands_pc_build_requests_to_the_sales_role():
    from app.agents.decentralized.support import support_node
    result = support_node({"messages": [HumanMessage(content="Quiero armar una PC gamer")]})
    tool_call = result["messages"][0].tool_calls[0]
    assert HANDOFF_TOOLS[tool_call["name"]] == "ventas"


def test_original_sales_registry_does_not_enable_automatic_pc_profiles():
    from app.agents.decentralized.sales import sales_tools
    assert not {"consultar_armados_pc", "modificar_armado_pc"} & {tool.name for tool in sales_tools}
