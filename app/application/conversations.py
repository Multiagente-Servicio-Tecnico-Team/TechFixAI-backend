"""Registro de conversaciones: dueño, patrón fijo y presupuesto pendiente.

Vive en memoria del proceso (una sola instancia de la API); la memoria de los
mensajes la guarda cada patrón con su checkpointer usando el mismo identificador.
"""
from dataclasses import dataclass, field
from threading import Lock, RLock
from uuid import uuid4

from app.domain.errors import ConversationNotFound, PatternLocked


@dataclass
class Conversation:
    id: str
    customer_id: int
    pattern: str
    pending_quote: bool = False
    # Serializa los turnos de una misma conversación.
    lock: Lock = field(default_factory=Lock, repr=False, compare=False)


class ConversationRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Conversation] = {}
        self._lock = RLock()

    def open(self, conversation_id: str | None, customer_id: int, pattern: str) -> Conversation:
        """Crea una conversación nueva o devuelve la existente si es del mismo cliente y patrón."""
        with self._lock:
            if conversation_id is None:
                conversation = Conversation(id=str(uuid4()), customer_id=customer_id, pattern=pattern)
                self._items[conversation.id] = conversation
                return conversation
            conversation = self._items.get(conversation_id)
            if conversation is None or conversation.customer_id != customer_id:
                raise ConversationNotFound()
            if conversation.pattern != pattern:
                raise PatternLocked()
            return conversation
