"""Lectura de «Mis Tickets» desde PostgreSQL (repositorio existente) hacia entidades de dominio."""
import logging
from collections.abc import Callable
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.application.errors import StorageUnavailable
from app.domain.tickets import CustomerTicket, TicketQuote, TicketQuoteLine

logger = logging.getLogger(__name__)
TICKETS_UNAVAILABLE = "No se pudieron cargar tus tickets en este momento."


class TicketRows(Protocol):
    """Lo mínimo que se usa de `ServiceRepository`."""

    def list_customer_tickets(self, customer_id: int) -> list[dict[str, Any]]: ...


def _default_repository() -> TicketRows:
    from app.database.repository import ServiceRepository

    return ServiceRepository()


class RepositoryTicketReader:
    def __init__(self, repository_factory: Callable[[], TicketRows] | None = None) -> None:
        self._repository_factory = repository_factory or _default_repository

    def list_for_customer(self, customer_id: int) -> list[CustomerTicket]:
        try:
            rows = self._repository_factory().list_customer_tickets(customer_id)
        except (SQLAlchemyError, OSError, RuntimeError) as exc:
            logger.error("Customer ticket listing failed: %s", type(exc).__name__)
            raise StorageUnavailable(TICKETS_UNAVAILABLE) from exc
        return [to_ticket(row) for row in rows]


def to_ticket(row: dict[str, Any]) -> CustomerTicket:
    quote = row.get("quote")
    return CustomerTicket(
        code=row["code"],
        title=row["title"],
        failure_description=row["failure_description"],
        request_type=row["request_type"],
        status=row["status"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        quote=(
            TicketQuote(
                status=quote["status"],
                labor_cost=quote["labor_cost"],
                parts_cost=quote["parts_cost"],
                total_amount=quote["total_amount"],
                created_at=quote["created_at"],
                lines=[
                    TicketQuoteLine(
                        name=line["name"],
                        quantity=line["quantity"],
                        unit_price=line["unit_price"],
                        subtotal=line["subtotal"],
                    )
                    for line in quote["lines"]
                ],
            )
            if quote
            else None
        ),
    )
