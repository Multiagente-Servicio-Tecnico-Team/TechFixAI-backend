from langchain_core.tools import tool
from app.agents.decentralized.tools.compras_tools import transferir_a_ventas as _sales


@tool(description=_sales.description)
def transfer_to_sales(reason: str) -> str:
    return _sales.invoke({"motivo": reason})


legacy_handoff_tools = [_sales]
