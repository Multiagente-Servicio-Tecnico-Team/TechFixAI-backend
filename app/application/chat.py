"""Caso de uso: enviar un mensaje (o pulsar aceptar/rechazar) al patrón elegido."""
from collections.abc import Mapping
from dataclasses import dataclass

from app.application.conversations import ConversationRegistry
from app.application.errors import RateLimited
from app.application.ports import AttemptLimiter, ChatPattern
from app.domain.chat import PatternReply, message_for_action
from app.domain.errors import NoPendingQuote


@dataclass(frozen=True)
class ChatTurn:
    conversation_id: str
    pattern: str
    reply: PatternReply


class SendChatMessage:
    def __init__(
        self,
        patterns: Mapping[str, ChatPattern],
        conversations: ConversationRegistry,
        limiter: AttemptLimiter,
        durable_conversations=None,
    ) -> None:
        self._patterns = patterns
        self._conversations = conversations
        self._limiter = limiter
        self._durable = durable_conversations

    def execute(
        self,
        *,
        customer_id: int,
        authenticated_role: str | None = None,
        pattern: str,
        message: str | None = None,
        action: str | None = None,
        conversation_id: str | None = None,
        proposal_id: str | None = None,
    ) -> ChatTurn:
        # El límite cuenta cada envío del cliente, aunque después falle.
        key = str(customer_id)
        if self._limiter.blocked(key):
            raise RateLimited()
        self._limiter.fail(key)

        if self._durable is not None:
            if pattern == "decentralized":
                cid, reply = self._durable.execute(customer_id=customer_id, authenticated_role=authenticated_role, message=message,
                    conversation_id=conversation_id, action=action, proposal_id=proposal_id)
                return ChatTurn(conversation_id=cid, pattern=pattern, reply=reply)
            self._durable.check_other_pattern(conversation_id, customer_id)
        if action in {"resume_payment", "resume_logistics", "resume_warranty"}:
            from app.application.errors import ConversationActionError
            raise ConversationActionError(409, "Accion no disponible para este patron.")
        conversation = self._conversations.open(conversation_id, customer_id, pattern)
        chat_pattern = self._patterns[pattern]
        if action and (not chat_pattern.supports_quotes or not conversation.pending_quote):
            raise NoPendingQuote()

        with conversation.lock:
            reply = chat_pattern.reply(conversation.id, customer_id, message_for_action(action, message))
            if chat_pattern.supports_quotes:
                conversation.pending_quote = reply.pending_quote
        return ChatTurn(conversation_id=conversation.id, pattern=pattern, reply=reply)
