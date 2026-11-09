from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.agents.decentralized.state import AgentState
from app.application.tickets import lookup_customer_ticket
from app.application.logistics import record_customer_logistics_preference
from app.application.warranties import lookup_customer_warranty, register_customer_warranty_claim
from app.database.repository import ServiceRepository

ticket_repository = ServiceRepository()


@tool
def consultar_estado_garantia(
    warranty_code: str,
    state: Annotated[AgentState, InjectedState()],
) -> str:
    """Consulta solo una póliza asociada al cliente autenticado."""
    warranty = lookup_customer_warranty(
        ticket_repository,
        customer_id=state.get("customer_id"),
        warranty_code=warranty_code,
    )
    if warranty is None:
        return "No encontré una póliza con ese código asociada a tu cuenta."
    end_date = warranty["end_date"]
    end_text = end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date)[:10]
    active = warranty.get("status") == "ACTIVE" and warranty.get("not_expired")
    label = "vigente" if active else "no vigente"
    return f"La póliza {warranty['warranty_code']} figura como {label} y vence el {end_text}."


@tool
def registrar_reclamo_garantia(
    warranty_code: str,
    reason: str,
    state: Annotated[AgentState, InjectedState()],
) -> str:
    """Registra un reclamo elegible como pendiente de evaluación."""
    if not state.get("ticket_id"):
        return "Para registrar el reclamo primero necesito un ticket de servicio asociado a tu cuenta."
    claim = register_customer_warranty_claim(
        ticket_repository,
        customer_id=state.get("customer_id"),
        ticket_id=state["ticket_id"],
        warranty_code=warranty_code,
        reason=reason,
    )
    return f"Registré el reclamo {claim['claim_code']} para revisión manual; no implica cobertura aprobada."


@tool
def registrar_preferencia_logistica(
    mode: Literal["PHYSICAL_STORE", "COURIER_SHIPMENT"],
    courier_company: str = "",
    shipping_address: str = "",
    state: Annotated[AgentState, InjectedState()] = None,
) -> str:
    """Registra preferencia logística de un ticket propio, pendiente de recepción."""
    if not state or not state.get("ticket_id"):
        return "Necesito un ticket asociado a tu cuenta para registrar la preferencia logística."
    record_customer_logistics_preference(
        ticket_repository,
        customer_id=state.get("customer_id"),
        ticket_id=state["ticket_id"],
        mode=mode,
        courier_company=courier_company or None,
        shipping_address=shipping_address or None,
    )
    return "Registré la preferencia logística como pendiente de recepción; no confirma pago ni entrega."


@tool
def transferir_a_soporte(motivo: str) -> str:
    """Devuelve a Soporte una consulta de ticket o atención general."""
    return f"TRANSFERIR_SOPORTE: {motivo}"


@tool
def consultar_estado_ticket(
    ticket_code: str,
    state: Annotated[AgentState, InjectedState()],
) -> str:
    """Consulta por código solo los tickets asociados a la cuenta autenticada."""
    ticket = lookup_customer_ticket(
        ticket_repository,
        customer_id=state.get("customer_id"),
        ticket_code=ticket_code,
    )
    if ticket is None:
        return "No encontré un ticket con ese código asociado a tu cuenta."
    return f"El ticket {ticket['code']} tiene estado {ticket['status']}."


@tool
def transferir_a_tecnico(motivo: str) -> str:
    """Transfiere una solicitud al agente Técnico."""
    return f"TRANSFERIR_TECNICO: {motivo}"


@tool
def transferir_a_ventas(motivo: str) -> str:
    """Transfiere una solicitud al agente de Ventas."""
    return f"TRANSFERIR_VENTAS: {motivo}"


@tool
def transferir_a_reembolsos(motivo: str) -> str:
    """Transfiere al flujo de solicitudes de reembolso sin procesar pagos."""
    return f"TRANSFERIR_REEMBOLSOS: {motivo}"


@tool
def transferir_a_compras(motivo: str) -> str:
    """Transfiere una solicitud de compra a proveedor."""
    return f"TRANSFERIR_COMPRAS: {motivo}"
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".support_tools", __package__)
