from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool
from app.application.warranties import lookup_customer_warranty, register_customer_warranty_claim
from app.database.repository import ServiceRepository


def make_warranty_agent(repository: ServiceRepository):
    def warranty_agent(state: ServiceState) -> dict[str, Any]:
        code = state.get("warranty_code", "").strip()
        if not code:
            return {
                "outcome": "warranty_code_required",
                "messages": [
                    AIMessage(content="Indícame el código exacto de la póliza de garantía.")
                ],
            }
        warranty = traced_tool(
            state,
            "warranty_lookup",
            lambda: lookup_customer_warranty(
                repository,
                customer_id=state["customer_id"],
                warranty_code=code,
            ),
        )
        if not warranty:
            return {
                "warranty_status": "NOT_FOUND",
                "outcome": "warranty_not_found",
                "messages": [
                    AIMessage(
                        content=(
                            "No encontré una póliza con ese código. Verifica el "
                            "código de tu comprobante; no hice cambios en la base."
                        )
                    )
                ],
            }
        if int(warranty["customer_id"]) != state["customer_id"]:
            return {
                "warranty_status": "NOT_FOUND",
                "outcome": "warranty_not_found",
                "messages": [
                    AIMessage(
                        content=(
                            "No encontré una póliza asociada a tu cuenta con ese "
                            "código. Verifícalo en tu comprobante."
                        )
                    )
                ],
            }

        status = str(warranty["status"])
        end_date = warranty["end_date"]
        end_date_text = (
            end_date.isoformat()
            if hasattr(end_date, "isoformat")
            else str(end_date)[:10]
        )
        is_active = status == "ACTIVE" and warranty["not_expired"]
        if state.get("request_type") != "WARRANTY_CLAIM":
            status_text = "vigente" if is_active else "no vigente"
            return {
                "warranty_id": int(warranty["id"]),
                "warranty_status": status,
                "outcome": "warranty_status_checked",
                "messages": [
                    AIMessage(
                        content=(
                            f"La póliza {warranty['warranty_code']} figura como "
                            f"{status_text} para {warranty['item_or_service_name']}. "
                            f"Vence el {end_date_text}. "
                            f"Estado registrado: {status}."
                        )
                    )
                ],
            }

        if not is_active:
            return {
                "warranty_id": int(warranty["id"]),
                "warranty_status": status,
                "outcome": "warranty_not_covered",
                "messages": [
                    AIMessage(
                        content=(
                            f"La póliza {warranty['warranty_code']} no aparece "
                            f"vigente (estado registrado: {status}; vencimiento: "
                            f"{end_date_text}). No registré un reclamo. "
                            "Si deseas una evaluación de reparación pagada, dímelo "
                            "y te orientaré por ese flujo."
                        )
                    )
                ],
            }

        claim = traced_tool(
            state,
            "warranty_claim_write",
            lambda: register_customer_warranty_claim(
                repository,
                ticket_id=state["ticket_id"],
                customer_id=state["customer_id"],
                warranty_code=code,
                reason=state["failure_description"],
            ),
        )
        claim_code = claim["claim_code"]
        return {
            "warranty_id": int(warranty["id"]),
            "warranty_status": status,
            "warranty_claim_code": claim_code,
            "ticket_status": "WARRANTY_IN_REVIEW",
            "awaiting_logistics": True,
            "logistics_ticket_id": state["ticket_id"],
            "outcome": "warranty_claim_registered",
            "messages": [
                AIMessage(
                    content=(
                        f"Registré el reclamo {claim_code} en estado de revisión. "
                        "La cobertura final requiere evaluación del equipo. Para "
                        "coordinar su recepción, indica si lo llevarás presencialmente "
                        "o lo enviarás por courier."
                    )
                )
            ],
        }

    return warranty_agent


def make_order_completion_agent(repository: ServiceRepository):
    def order_completion_agent(state: ServiceState) -> dict[str, Any]:
        parts = state.get("matched_parts", [])
        item_name = (
            "Armado de PC"
            if state.get("request_type") == "PC_BUILD"
            else "Venta de productos"
        )
        if parts:
            item_name += ": " + ", ".join(
                str(part["name"]) for part in parts
            )
        warranty = traced_tool(
            state,
            "warranty_write",
            lambda: repository.create_order_warranty(
                ticket_id=state["ticket_id"],
                quote_id=state["quote_id"],
                customer_id=state["customer_id"],
                warranty_code=f"WAR-{uuid4().hex[:12].upper()}",
                item_or_service_name=item_name,
                warranty_months=3,
                request_type=state["request_type"],
            ),
        )
        return {
            "warranty_id": int(warranty["id"]),
            "warranty_code": warranty["warranty_code"],
            "warranty_status": "ACTIVE",
            "outcome": "order_completed",
            "messages": [
                AIMessage(
                    content=(
                        f"Registré la garantía de 3 meses con el código "
                        f"{warranty['warranty_code']} para el ticket "
                        f"{state['ticket_code']}. Tu pago continúa pendiente y la "
                        "logística está pendiente de recepción; esto no confirma "
                        "reserva ni entrega."
                        + (
                            " El equipo será revisado por el técnico cuando ingrese "
                            "físicamente al taller."
                            if state.get("request_type") == "PC_BUILD"
                            else " Te avisaremos cuando el pedido esté listo para "
                            "retiro o despacho."
                        )
                        + " Gracias por tu preferencia. ¡Que tengas un buen día!"
                    )
                )
            ],
        }

    return order_completion_agent
