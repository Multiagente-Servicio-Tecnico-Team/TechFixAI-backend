"""Puertos de la aplicación: lo que los casos de uso necesitan del exterior.

Cada patrón multiagente (Jerárquico, Orquestador, Red descentralizada) se consume
como un servicio que cumple `ChatPattern`; así el chat y las pruebas funcionan con
cualquiera de ellos y la comparación usa la misma entrada.
"""
from typing import Protocol, runtime_checkable

from app.domain.chat import PatternReply
from app.domain.tickets import CustomerTicket


@runtime_checkable
class ChatPattern(Protocol):
    """Un patrón LangGraph visto desde la aplicación."""

    id: str
    name: str
    # False si el patrón no propone presupuestos (los botones aceptar/rechazar no aplican).
    supports_quotes: bool

    def reply(self, conversation_id: str, customer_id: int, message: str) -> PatternReply:
        """Procesa un turno. La memoria de la conversación es responsabilidad del patrón."""
        ...


class CustomerTicketReader(Protocol):
    def list_for_customer(self, customer_id: int) -> list[CustomerTicket]:
        """Solo los tickets del cliente indicado, con su último presupuesto."""
        ...


class AttemptLimiter(Protocol):
    """Límite de intentos por clave en una ventana de tiempo."""

    def blocked(self, key: str) -> bool: ...

    def fail(self, key: str) -> None: ...
