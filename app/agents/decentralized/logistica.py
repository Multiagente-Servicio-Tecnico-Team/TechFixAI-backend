"""Deterministic logistics intake; separate checkpointed step performs the insert.

No LLM receives address/contact fields. No workshop information is fabricated.
"""
import re
from langchain_core.messages import AIMessage
from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import latest_user_message, normalize_text
from app.agents.decentralized.logistics_operations import logistics_payload, validate_pending_logistics_operation
from app.agents.decentralized.ticket_operations import _revision
from app.database.decentralized_repository import _id, RetryConflict
from app.agents.decentralized.tools.logistics_handoff_tools import transfer_to_support

logistica_tools = [transfer_to_support]


def collect_logistics(state):
    """Only explicit user choices/labelled fields; never infer carrier or dates."""
    data = dict(state.get("logistics") or {})
    text = latest_user_message(state)
    normalized = normalize_text(text)
    courier = bool(re.search(r"\bcourier\b",normalized)) and not re.search(r"\b(?:no|sin|no quiero|no prefiero)\s+(?:por\s+)?courier\b",normalized)
    physical = any(word in normalized for word in ("retiro presencial", "entrega presencial", "ingreso presencial")) and not re.search(r"\b(?:no|sin|no quiero|no prefiero)\s+(?:retiro|entrega|ingreso) presencial",normalized)
    if courier and physical:
        data.pop("mode",None)
    elif courier:
        data["mode"] = "COURIER_SHIPMENT"
    elif physical:
        data["mode"] = "PHYSICAL_STORE"
    fields = {"courier": "courier_company", "empresa": "courier_company", "direccion": "shipping_address",
              "destinatario": "recipient_name", "telefono": "recipient_phone"}
    # Semicolon/newline delimited explicit labels. Preserve original user values.
    for segment in re.split(r"[;\n]", text):
        label, separator, value = segment.partition(":")
        key = fields.get(normalize_text(label.strip()))
        if separator and key and value.strip():
            data[key] = value.strip()
    return data


def logistica_node(state: AgentState, *, repository=None, authenticated_customer_id=None):
    def response(text):
        return {"current_agent": "logistica", "logistics_preparation_ready": False,
                "messages": [AIMessage(content=text)]}
    if repository is None or authenticated_customer_id is None:
        return response("Necesito un ticket existente y una consulta autorizada para coordinar logística. No se ha registrado recepción ni despacho.")
    try:
        customer = _id(authenticated_customer_id)
        if _id(state.get("customer_id")) != customer:
            raise RetryConflict("Identidad incompatible")
        ticket_id = _id(state.get("ticket_id"))
        ticket = repository.get_logistics_context(customer_id=customer, ticket_id=ticket_id)
        if ticket["id"] != ticket_id or ticket["customer_id"] != customer:
            raise RetryConflict("Ticket incompatible")
        revision = _revision(state.get("request_revision"))
        data = collect_logistics(state)
        if data.get("mode") not in {"PHYSICAL_STORE", "COURIER_SHIPMENT"}:
            return response("¿Prefieres ingreso o retiro presencial, o courier? No se ha registrado una operación logística.")
        if data["mode"] == "COURIER_SHIPMENT":
            required = ["courier_company"]
            if ticket["request_type"] in {"SALE", "PC_BUILD"}:
                required += ["shipping_address", "recipient_name", "recipient_phone"]
            missing = [key for key in required if not isinstance(data.get(key), str) or not data[key].strip()]
            if missing:
                labels = {"courier_company":"empresa de courier", "shipping_address":"dirección o agencia de entrega",
                          "recipient_name":"nombre del destinatario", "recipient_phone":"teléfono del destinatario"}
                update = response("Falta indicar: " + ", ".join(labels[key] for key in missing) + ". No hay envío confirmado.")
                update["logistics"] = data
                return update
        payload = logistics_payload(customer_id=customer, ticket_id=ticket_id,
                                    request_type=ticket["request_type"], data=data)
        pending = dict(request_revision=revision, request_type=ticket["request_type"], payload=payload)
        existing = state.get("pending_logistics_operation")
        if existing is not None:
            existing = validate_pending_logistics_operation(existing, authenticated_customer_id=customer, request_revision=revision)
            if existing != pending:
                raise RetryConflict("Operación pendiente distinta")
        update = response("Los datos logísticos están preparados. Confirma la reanudación para registrar el estado inicial pendiente; no confirma equipo recibido, producto listo, despacho ni entrega.")
        update.update(pending_logistics_operation=pending, logistics_preparation_ready=True,
                      logistics={key:value for key,value in payload.items()
                      if key not in {"customer_id", "ticket_id"}})
        return update
    except RetryConflict:
        # Do not return a normal patch with the old pending operation still in
        # state: the router would otherwise schedule that superseded content.
        raise
    except LookupError:
        return response("No se encontró un ticket autorizado para esta coordinación.")
    except (ValueError, KeyError, TypeError):
        return response("No se cumplen los datos o precondiciones persistidas del flujo. Ventas y ensamblaje requieren cotización aceptada y pago registrado; garantía requiere póliza y reclamo verificables. No se registró logística.")
    except Exception:
        return response("No fue posible verificar logística en el almacenamiento. No se ha confirmado recepción, despacho ni entrega.")
