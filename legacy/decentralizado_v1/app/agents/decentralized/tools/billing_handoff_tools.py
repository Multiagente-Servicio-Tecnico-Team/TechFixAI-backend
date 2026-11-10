from langchain_core.tools import tool
from app.agents.decentralized.tools.facturacion_tools import transferir_a_soporte as _support
from app.agents.decentralized.tools.facturacion_tools import transferir_a_ventas as _sales
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica as _logistics


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


@tool(description=_sales.description)
def transfer_to_sales(reason: str) -> str:
    return _sales.invoke({"motivo": reason})


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


legacy_handoff_tools = [_support, _sales, _logistics]
