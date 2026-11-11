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


@tool
def transfer_to_refund(reason: str) -> str:
    """Deriva una solicitud de reembolso al registro de revisión manual."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("El motivo de transferencia es obligatorio.")
    return f"TRANSFER_REFUND: {reason.strip()}"


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


@tool(description=_warranty.description)
def transfer_to_warranty(reason: str) -> str:
    return _warranty.invoke({"motivo": reason})


@tool
def transfer_to_faq(reason: str) -> str:
    """Deriva una pregunta informativa al agente FAQ y al corpus Markdown común."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("El motivo de transferencia es obligatorio.")
    return f"TRANSFER_FAQ: {reason.strip()}"


@tool
def transfer_to_out_of_scope(reason: str) -> str:
    """Deriva una consulta ajena al negocio al agente de fuera de dominio."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("El motivo de transferencia es obligatorio.")
    return f"TRANSFER_OUT_OF_SCOPE: {reason.strip()}"


legacy_handoff_tools = [
    _warranty, _logistics, _billing, _hardware, _sales, _software,
    transfer_to_refund, transfer_to_faq, transfer_to_out_of_scope,
]
