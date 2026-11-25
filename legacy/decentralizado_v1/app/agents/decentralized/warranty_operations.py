"""Immutable warranty operations; identity and authorization come from the server."""
from secrets import token_hex
from app.database.decentralized_repository import _id, _text, RetryConflict
from app.agents.decentralized.ticket_operations import _revision


def validate_pending_warranty_operation(operation, *, authenticated_customer_id, request_revision):
    if not isinstance(operation, dict) or set(operation) != {"request_revision", "payload"}:
        raise ValueError("Operación de garantía inválida")
    if _revision(operation["request_revision"]) != _revision(request_revision):
        raise RetryConflict("Revisión de garantía incompatible")
    payload = operation["payload"]
    if not isinstance(payload, dict) or set(payload) != {"customer_id", "ticket_id", "warranty_code", "claim_code", "reason"}:
        raise ValueError("Contenido de reclamo inválido")
    normalized = dict(customer_id=_id(payload["customer_id"]), ticket_id=_id(payload["ticket_id"]),
        warranty_code=_text(payload["warranty_code"], 50), claim_code=_text(payload["claim_code"], 50),
        reason=_text(payload["reason"]))
    if normalized != payload or normalized["customer_id"] != _id(authenticated_customer_id):
        raise RetryConflict("Contenido o identidad incompatible")
    return dict(request_revision=request_revision, payload=normalized)


def prepare_warranty_claim(state, *, authenticated_customer_id, warranty_code, reason):
    customer = _id(authenticated_customer_id)
    if state.get("customer_id") != customer:
        raise RetryConflict("Identidad incompatible")
    revision = _revision(state.get("request_revision"))
    existing = state.get("pending_warranty_operation")
    payload = dict(customer_id=customer, ticket_id=_id(state.get("ticket_id")),
        warranty_code=_text(warranty_code, 50), reason=_text(reason))
    if existing is not None:
        existing = validate_pending_warranty_operation(existing, authenticated_customer_id=customer, request_revision=revision)
        if any(existing["payload"][key] != value for key, value in payload.items()):
            raise RetryConflict("Reclamo pendiente diferente")
        return existing
    return dict(request_revision=revision, payload={**payload, "claim_code": "CLM-" + token_hex(12)})
