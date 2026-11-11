"""Use cases and validation for direct product sales quotations."""
from datetime import datetime
from typing import Any, Protocol

from app.domain.customer_commerce import validate_sale_quote_expiry


def validate_direct_sale_acceptance(
    quote: dict[str, Any], *, now: datetime, customer_id: int | None = None,
) -> int:
    quote_id = quote.get("id")
    if type(quote_id) is not int or quote_id < 1:
        raise ValueError("La cotización requiere un identificador válido.")
    if quote.get("kind", quote.get("quote_type")) != "DIRECT_SALE":
        raise ValueError("La aceptación aplica únicamente a una cotización de venta directa.")
    if quote.get("status") != "PENDING":
        raise ValueError("La cotización debe estar pendiente para aceptarse.")
    if customer_id is not None:
        if type(customer_id) is not int or customer_id < 1:
            raise ValueError("El identificador del cliente debe ser positivo.")
        if quote.get("customer_id") != customer_id:
            raise PermissionError("La cotización no pertenece al cliente autenticado.")
    expires_at = quote.get("expires_at")
    if not isinstance(expires_at, datetime):
        raise ValueError("La cotización de venta requiere vencimiento.")
    validate_sale_quote_expiry(expires_at, now=now)
    return quote_id


class DirectSalesQuoteWriter(Protocol):
    def accept_direct_sales_quote(
        self, *, quote_id: int, customer_id: int, actor_user_id: int,
        idempotency_key: str,
    ) -> dict[str, Any]: ...


class AcceptDirectSalesQuote:
    def __init__(self, writer_factory):
        self._writer_factory = writer_factory

    def execute(
        self, *, quote_id: int, customer_id: int, actor_user_id: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if type(customer_id) is not int or customer_id < 1:
            raise PermissionError("Se requiere el cliente comercial de la sesión.")
        if type(actor_user_id) is not int or actor_user_id < 1:
            raise PermissionError("Se requiere una cuenta autenticada para registrar la aceptación.")
        key = idempotency_key.strip()
        if not key or len(key) > 200:
            raise ValueError("La clave de idempotencia no es válida.")
        return self._writer_factory().accept_direct_sales_quote(
            quote_id=quote_id, customer_id=customer_id,
            actor_user_id=actor_user_id, idempotency_key=key,
        )
