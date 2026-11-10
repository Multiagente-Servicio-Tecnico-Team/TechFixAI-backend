"""Ticket operation contracts only: no SQL, model calls or persistence.

Trusted caller supplies authenticated_customer_id; state alone is not authentication.
Code generation is separate so preparation and validation remain pure.
"""
from base64 import b32encode
from secrets import token_bytes

from app.agents.decentralized.state import (
    PendingTicketOperation, request_type_for_intent,
)
from app.database.decentralized_repository import RetryConflict, _id, _text


def generate_ticket_code():
    """80 random bits; database UNIQUE remains the final collision protection."""
    return "TCK-" + b32encode(token_bytes(10)).decode("ascii")


def _revision(value):
    if type(value) is not int or value < 0:
        raise ValueError("Revisión de solicitud inválida")
    return value


def validate_pending_ticket_operation(operation, *, authenticated_customer_id,
                                      request_revision):
    """Return a detached validated copy; never normalize a stored payload silently."""
    customer = _id(authenticated_customer_id)
    revision = _revision(request_revision)
    if not isinstance(operation, dict) or set(operation) != {"request_revision", "payload"}:
        raise ValueError("Contrato de operación inválido")
    if _revision(operation["request_revision"]) != revision:
        raise RetryConflict("Operación de otra revisión")
    payload = operation["payload"]
    if not isinstance(payload, dict) or set(payload) != {
        "customer_id", "code", "title", "failure_description", "request_type"
    }:
        raise ValueError("Contenido de operación inválido")
    if _id(payload["customer_id"]) != customer:
        raise RetryConflict("Operación de otro cliente")
    request_type = request_type_for_intent(payload["request_type"])
    if request_type is None:
        raise ValueError("Tipo no persistible")
    normalized = dict(customer_id=customer, code=_text(payload["code"], 20),
                      title=_text(payload["title"], 200),
                      failure_description=_text(payload["failure_description"]),
                      request_type=request_type)
    if normalized != payload:
        raise ValueError("Contenido pendiente no normalizado")
    return PendingTicketOperation(request_revision=revision, payload=normalized)


def prepare_pending_ticket_operation(state, *, authenticated_customer_id,
                                     intent, title, failure_description, code=None):
    """Pure patch. Initial preparation requires a previously generated code.

    This validates payload shape, not semantic intake completeness or DB privileges.
    An informational request returns no patch; it cannot discard pending work.
    """
    customer = _id(authenticated_customer_id)
    if state.get("customer_id") is not None and _id(state["customer_id"]) != customer:
        raise RetryConflict("Identidad incompatible con la conversación")
    revision = _revision(state.get("request_revision"))
    pending = state.get("pending_ticket_operation")
    request_type = request_type_for_intent(intent)
    if request_type is None:
        if pending is not None:
            raise RetryConflict("No se puede descartar la operación pendiente")
        return {}
    if any(state.get(key) is not None for key in ("ticket_id", "ticket_code", "ticket_status")):
        raise RetryConflict("La solicitud ya está vinculada a un ticket confirmado")
    if pending is not None:
        pending = validate_pending_ticket_operation(pending,
            authenticated_customer_id=customer, request_revision=revision)
        if code is not None and code != pending["payload"]["code"]:
            raise RetryConflict("No se puede sustituir el código pendiente")
        code = pending["payload"]["code"]
    prepared = PendingTicketOperation(request_revision=revision, payload=dict(
        customer_id=customer, code=_text(code, 20), title=_text(title, 200),
        failure_description=_text(failure_description), request_type=request_type))
    if pending is not None and prepared != pending:
        raise RetryConflict("Contenido distinto para la operación pendiente")
    return {"pending_ticket_operation": prepared}
