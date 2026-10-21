"""Caso de uso: listar los tickets del cliente de la sesión («Mis Tickets»)."""
from collections.abc import Callable

from app.application.ports import CustomerTicketReader
from app.domain.tickets import CustomerTicket


class ListCustomerTickets:
    def __init__(self, reader_factory: Callable[[], CustomerTicketReader]) -> None:
        # Se crea por petición: la conexión a la base de datos no se abre al iniciar la API.
        self._reader_factory = reader_factory

    def execute(self, customer_id: int) -> list[CustomerTicket]:
        return self._reader_factory().list_for_customer(customer_id)
