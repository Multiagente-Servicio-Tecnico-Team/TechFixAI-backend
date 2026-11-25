from langchain_core.tools import tool
from app.agents.decentralized.tools.almacen_tools import transferir_a_ventas as _sales, transferir_a_compras as _purchasing


@tool(description=_sales.description)
def transfer_to_sales(reason: str) -> str:
    return _sales.invoke({"motivo": reason})


@tool(description=_purchasing.description)
def transfer_to_purchasing(reason: str) -> str:
    return _purchasing.invoke({"motivo": reason})


legacy_handoff_tools = [_sales, _purchasing]
