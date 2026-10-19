from langchain_core.tools import tool

from app.agents.decentralized.tools.soporte_tools import (
    transferir_a_tecnico as _hardware,
    transferir_a_ventas as _sales,
    transferir_a_software as _software,
)
from app.agents.decentralized.tools.facturacion_tools import transferir_a_facturacion as _billing
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica as _logistics
from app.agents.decentralized.tools.garantia_tools import transferir_a_garantia as _warranty


@tool(description=_hardware.description)
def transfer_to_hardware(reason: str) -> str:
    return _hardware.invoke({"motivo": reason})


@tool(description=_sales.description)
def transfer_to_sales(reason: str) -> str:
    return _sales.invoke({"motivo": reason})


@tool(description=_software.description)
def transfer_to_software(reason: str) -> str:
    return _software.invoke({"motivo": reason})


@tool(description=_billing.description)
def transfer_to_billing(reason: str) -> str:
    return _billing.invoke({"motivo": reason})


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


@tool(description=_warranty.description)
def transfer_to_warranty(reason: str) -> str:
    return _warranty.invoke({"motivo": reason})


legacy_handoff_tools = [_warranty, _logistics, _billing, _hardware, _sales, _software]
