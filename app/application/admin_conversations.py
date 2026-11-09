"""Conversaciones y propuestas ADMIN efímeras, aisladas por actor y patrón."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock, RLock
from uuid import uuid4

from app.application.capabilities import CapabilityError


@dataclass
class PendingProposal:
    id: str
    capability: str
    arguments: dict
    preview: dict
    expires_at: datetime
    status: str = "PENDING_CONFIRMATION"
    result: dict | None = None
    lock: Lock = field(default_factory=Lock, repr=False, compare=False)


@dataclass
class AdminConversation:
    id: str
    actor_id: int
    role: str
    pattern: str
    history: list[tuple[str, str]] = field(default_factory=list)
    pending: PendingProposal | None = None
    lock: RLock = field(default_factory=RLock, repr=False, compare=False)


class AdminConversationRegistry:
    """Memoria intencionalmente local; reinicio/otra instancia pierde propuestas."""

    def __init__(self, *, proposal_ttl_seconds: int = 300, max_history_turns: int = 8):
        self._ttl = proposal_ttl_seconds
        self._max_history = max_history_turns
        self._items: dict[str, AdminConversation] = {}
        self._lock = RLock()

    def open(self, conversation_id: str | None, *, actor_id: int, role: str, pattern: str) -> AdminConversation:
        with self._lock:
            if conversation_id is None:
                item = AdminConversation(str(uuid4()), actor_id, role, pattern)
                self._items[item.id] = item
                return item
            item = self._items.get(str(conversation_id))
            if item is None or item.actor_id != actor_id or item.role != role:
                raise CapabilityError("conversation_not_found", "No se encontró esa conversación para tu sesión.", 404)
            if item.pattern != pattern:
                raise CapabilityError("pattern_locked", "La conversación pertenece a otro patrón.", 409)
            return item

    def propose(self, conversation: AdminConversation, capability: str, arguments: dict, preview: dict) -> PendingProposal:
        proposal = PendingProposal(
            id=str(uuid4()), capability=capability, arguments=arguments, preview=preview,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self._ttl),
        )
        conversation.pending = proposal
        return proposal

    def add_turn(self, conversation: AdminConversation, user: str, assistant: str) -> None:
        conversation.history.extend((("user", user), ("assistant", assistant)))
        conversation.history[:] = conversation.history[-self._max_history * 2:]

    @staticmethod
    def discard_pending(conversation: AdminConversation, *, status: str = "CANCELLED") -> None:
        if conversation.pending and conversation.pending.status == "PENDING_CONFIRMATION":
            conversation.pending.status = status
            conversation.pending = None
