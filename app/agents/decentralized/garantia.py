"""Deterministic warranty queries and checkpointable claims. No LLM authorizes writes."""
from langchain_core.messages import AIMessage
from app.agents.decentralized.policy import handoff, latest_user_message
from app.agents.decentralized.warranty_operations import prepare_warranty_claim
from app.agents.decentralized.tools.garantia_tools import garantia_tools
from app.database.decentralized_repository import RetryConflict, _id
import re


def garantia_node(state, *, repository=None, authenticated_customer_id=None):
    def response(text, **patch):
        return {"current_agent": "garantia", "warranty_preparation_ready": False,
                "messages": [AIMessage(content=text)], **patch}
    if repository is None or authenticated_customer_id is None:
        return response("Necesito una consulta autenticada y el código exacto de garantía.")
    try:
        customer = _id(authenticated_customer_id)
        if state.get("customer_id") != customer:
            raise RetryConflict("Identidad incompatible")
        code = (state.get("intake") or {}).get("warranty_code") or state.get("warranty_code")
        # Explicit labelled user input, never fabricate or search by DNI.
        text = latest_user_message({**state, "messages": state.get("messages", [])})
        reported = re.findall(r"\bWAR-[A-Za-z0-9-]+\b", text, flags=re.I)
        if len(set(reported)) > 1:
            return response("Indica un único código de garantía para esta consulta.")
        if reported:
            if len(reported[0]) > 50:
                return response("El código de garantía supera el límite admitido; verifícalo.")
            if code and code != reported[0] and (state.get("pending_warranty_operation") or state.get("warranty_claim_id")):
                raise RetryConflict("Cambio de póliza con reclamo existente")
            code = reported[0]
        if not code and text.strip().startswith("Código:"):
            code = text.strip().partition(":")[2].strip()
        if not code:
            return response("Indica el código exacto de la garantía (Código: ...). La emisión requiere autorización comercial del servidor; no está habilitada por mensajes.")
        warranty = repository.get_warranty(customer_id=customer, warranty_code=code)
        patch = {"warranty_id": warranty["id"], "warranty_code": warranty["warranty_code"],
                 "warranty": {key: warranty[key] for key in ("status", "start_date", "end_date", "warranty_months", "item_or_service_name")}}
        if state.get("intent") != "WARRANTY_CLAIM":
            return response("La garantía está " + warranty["effective_status"] + ". Vencimiento: " + str(warranty["end_date"]) + ".", **patch)
        if state.get("warranty_claim_id"):
            claim = repository.get_warranty_claim(customer_id=customer, claim_id=state["warranty_claim_id"])
            if claim["ticket_id"] != state.get("ticket_id") or claim["warranty_id"] != warranty["id"]:
                raise RetryConflict("Reclamo incompatible")
            repository.get_logistics_context(customer_id=customer, ticket_id=claim["ticket_id"])
            return {**patch, **handoff("garantia", "transferir_a_logistica", motivo="Coordinar ingreso de reclamo persistido IN_REVIEW")}
        if warranty["effective_status"] != "ACTIVE":
            return response("La garantía no está vigente para registrar un reclamo. Una reparación pagada requiere una solicitud explícita independiente.", **patch)
        ticket = repository.get_ticket(customer_id=customer, ticket_id=state.get("ticket_id"))
        if ticket["request_type"] != "WARRANTY_CLAIM" or ticket["status"] != "NEW":
            return response("Se requiere un ticket de reclamo existente en estado NEW.", **patch)
        reason = (state.get("warranty_claim") or {}).get("reason") or ticket["failure_description"]
        operation = prepare_warranty_claim(state, authenticated_customer_id=customer, warranty_code=code, reason=reason)
        return response("Reclamo preparado; requiere reanudación explícita. Todavía no está registrado ni aprobado.",
            **patch, pending_warranty_operation=operation, warranty_preparation_ready=True)
    except RetryConflict:
        raise
    except LookupError:
        return response("No se encontró una garantía o ticket autorizado.")
    except (ValueError, TypeError, KeyError):
        return response("Faltan datos o condiciones verificadas para esta operación de garantía.")
    except Exception:
        return response("No fue posible verificar la garantía en el almacenamiento. No se ha confirmado ninguna operación.")
