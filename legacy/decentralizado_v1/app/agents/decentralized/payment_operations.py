"""Pure payment preparation, not evidence of SQL acceptance or a confirmed payment."""
from base64 import b32encode
from secrets import token_bytes
from app.database.decentralized_repository import _id, _text, RetryConflict
from app.agents.decentralized.ticket_operations import _revision


def generate_payment_code():
    return "PAY-" + b32encode(token_bytes(16)).decode("ascii").rstrip("=")


def validate_pending_payment_operation(operation, *, authenticated_customer_id, request_revision):
    customer = _id(authenticated_customer_id)
    revision = _revision(request_revision)
    if not isinstance(operation, dict) or set(operation) != {"request_revision", "payload"}:
        raise ValueError("Contrato de pago inválido")
    if _revision(operation["request_revision"]) != revision:
        raise RetryConflict("Pago pendiente de otra revisión")
    payload = operation["payload"]
    if not isinstance(payload, dict) or set(payload) != {"customer_id", "ticket_id", "quote_id", "payment_code"}:
        raise ValueError("Contenido de pago inválido")
    result = dict(customer_id=_id(payload["customer_id"]), ticket_id=_id(payload["ticket_id"]),
                  quote_id=_id(payload["quote_id"]), payment_code=_text(payload["payment_code"], 50))
    if result["customer_id"] != customer:
        raise RetryConflict("Pago pendiente de otro cliente")
    if result != payload:
        raise ValueError("Pago pendiente no normalizado")
    return dict(request_revision=revision, payload=result)


def prepare_pending_payment_operation(state, *, authenticated_customer_id, payment_code=None):
    customer = _id(authenticated_customer_id)
    if _id(state.get("customer_id")) != customer:
        raise RetryConflict("Identidad incompatible")
    revision = _revision(state.get("request_revision"))
    if state.get("payment_id") is not None or state.get("payment_code") is not None:
        raise RetryConflict("Pago ya confirmado")
    pending = state.get("pending_payment_operation")
    if pending is not None:
        pending = validate_pending_payment_operation(pending,
            authenticated_customer_id=customer, request_revision=revision)
        if payment_code is not None and payment_code != pending["payload"]["payment_code"]:
            raise RetryConflict("Código pendiente distinto")
        payment_code = pending["payload"]["payment_code"]
    operation = dict(request_revision=revision, payload=dict(customer_id=customer,
        ticket_id=_id(state.get("ticket_id")), quote_id=_id(state.get("quote_id")),
        payment_code=_text(payment_code, 50)))
    if pending is not None and operation != pending:
        raise RetryConflict("Contenido de pago pendiente distinto")
    return {"pending_payment_operation": operation}
