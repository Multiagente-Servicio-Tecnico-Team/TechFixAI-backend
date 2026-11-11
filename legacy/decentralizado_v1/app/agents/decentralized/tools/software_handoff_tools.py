from typing import Literal

from langchain_core.tools import tool

from app.agents.decentralized.tools.software_tools import (
    transferir_a_soporte as _support,
    transferir_a_tecnico as _hardware,
    transferir_a_ventas as _sales,
)
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica as _logistics


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


@tool(description=_hardware.description)
def transfer_to_hardware(reason: str) -> str:
    return _hardware.invoke({"motivo": reason})


@tool(description=_sales.description.replace("transferir_a_tecnico", "transfer_to_hardware"))
def transfer_to_sales(reason: str, scope: Literal["solo_servicio"]) -> dict:
    return _sales.invoke({"motivo": reason, "alcance": scope})


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


legacy_handoff_tools = [_support, _hardware, _sales, _logistics]
