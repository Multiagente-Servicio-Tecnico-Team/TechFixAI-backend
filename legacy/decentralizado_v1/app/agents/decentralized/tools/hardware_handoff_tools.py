from typing import Literal
from langchain_core.tools import tool
from app.agents.decentralized.tools.soporte_tools import transferir_a_soporte as _support, transferir_a_software as _software
from app.agents.decentralized.tools.tecnico_tools import transferir_a_ventas as _sales, transferir_a_almacen as _warehouse
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica as _logistics


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


@tool(description=_software.description)
def transfer_to_software(reason: str) -> str:
    return _software.invoke({"motivo": reason})


@tool(description=_sales.description)
def transfer_to_sales(reason: str, scope: Literal["solo_servicio", "repuestos", "sin_determinar"], part_name: str = "", quantity: int = 1) -> dict:
    return _sales.invoke({"motivo": reason, "alcance": scope, "nombre_repuesto": part_name, "cantidad": quantity})


@tool(description=_warehouse.description)
def transfer_to_warehouse(reason: str, part_name: str, quantity: int = 1) -> dict:
    return _warehouse.invoke({"motivo": reason, "nombre_repuesto": part_name, "cantidad": quantity})


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


legacy_handoff_tools = [_logistics, _support, _software, _sales, _warehouse]
