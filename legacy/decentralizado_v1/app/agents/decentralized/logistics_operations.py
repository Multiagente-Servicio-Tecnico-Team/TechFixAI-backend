"""Pure initial-logistics payload validation; no physical operation inferred."""
from app.database.decentralized_repository import _id, _text, RetryConflict
from app.agents.decentralized.ticket_operations import _revision


def logistics_payload(*, customer_id, ticket_id, request_type, data):
    if not isinstance(data, dict):
        raise ValueError("Datos logísticos inválidos")
    mode = data.get("mode")
    if mode not in {"PHYSICAL_STORE", "COURIER_SHIPMENT"}:
        raise ValueError("Elige retiro presencial o courier")
    if data.get("status", "PENDING_RECEIPT") != "PENDING_RECEIPT":
        raise ValueError("Estado inicial inválido")
    if any(data.get(key) is not None for key in ("tracking_number", "scheduled_date", "received_at", "delivered_at")):
        raise ValueError("No hay evidencia operativa para fechas o seguimiento")
    fields = dict(courier_company=None, shipping_address=None, recipient_name=None, recipient_phone=None)
    if mode == "COURIER_SHIPMENT":
        fields["courier_company"] = _text(data.get("courier_company"), 100)
        if request_type in {"SALE", "PC_BUILD"}:
            fields.update(shipping_address=_text(data.get("shipping_address")),
                          recipient_name=_text(data.get("recipient_name"), 150),
                          recipient_phone=_text(data.get("recipient_phone"), 20))
    # Receiving an equipment shipment requires carrier, not a customer delivery
    # address. PHYSICAL_STORE never persists unnecessary address/contact data.
    return dict(customer_id=_id(customer_id), ticket_id=_id(ticket_id), mode=mode, **fields)


def validate_pending_logistics_operation(operation, *, authenticated_customer_id, request_revision):
    if not isinstance(operation, dict) or set(operation) != {"request_revision", "request_type", "payload"}:
        raise ValueError("Operación logística inválida")
    if _revision(operation["request_revision"]) != _revision(request_revision):
        raise RetryConflict("Operación logística de otra revisión")
    payload = operation["payload"]
    if not isinstance(payload, dict) or set(payload) != {"customer_id", "ticket_id", "mode", "courier_company", "shipping_address", "recipient_name", "recipient_phone"}:
        raise ValueError("Contenido logístico inválido")
    if _id(payload["customer_id"]) != _id(authenticated_customer_id):
        raise RetryConflict("Operación logística de otro cliente")
    if operation["request_type"] not in {"REPAIR", "SUPPORT", "SALE", "PC_BUILD", "WARRANTY_CLAIM"}:
        raise ValueError("Tipo de solicitud inválido")
    normalized = logistics_payload(customer_id=authenticated_customer_id, ticket_id=payload["ticket_id"],
        request_type=operation["request_type"], data=payload)
    if normalized != payload:
        raise ValueError("Contenido logístico no normalizado")
    return dict(request_revision=request_revision, request_type=operation["request_type"], payload=normalized)
