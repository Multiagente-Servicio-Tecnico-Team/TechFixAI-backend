"""Caso de uso: listar los tickets del cliente de la sesión («Mis Tickets»)."""
from collections.abc import Callable

from app.application.ports import CustomerTicketReader
from app.domain.tickets import CustomerTicket


def lookup_customer_ticket(repository, *, customer_id: int, ticket_code: str):
    """Return one exact ticket code from the authenticated customer's list."""
    if type(customer_id) is not int or customer_id < 1:
        raise PermissionError("Se requiere una sesión de cliente autenticada.")
    code = ticket_code.strip().upper()
    if not code or len(code) > 20:
        return None
    tickets = repository.list_customer_tickets(customer_id)
    return next(
        (ticket for ticket in tickets if str(ticket.get("code", "")).upper() == code),
        None,
    )


class ListCustomerTickets:
    def __init__(self, reader_factory: Callable[[], CustomerTicketReader]) -> None:
        # Se crea por petición: la conexión a la base de datos no se abre al iniciar la API.
        self._reader_factory = reader_factory

    def execute(self, customer_id: int) -> list[CustomerTicket]:
        return self._reader_factory().list_for_customer(customer_id)
