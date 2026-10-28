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
    ) -> None:
        self._patterns = patterns
        self._conversations = conversations
        self._limiter = limiter

    def execute(
        self,
        *,
        customer_id: int,
        pattern: str,
        message: str | None = None,
        action: str | None = None,
        conversation_id: str | None = None,
    ) -> ChatTurn:
        # El límite cuenta cada envío del cliente, aunque después falle.
        key = str(customer_id)
        if self._limiter.blocked(key):
            raise RateLimited()
        self._limiter.fail(key)

        conversation = self._conversations.open(conversation_id, customer_id, pattern)
        chat_pattern = self._patterns[pattern]
        if action and (not chat_pattern.supports_quotes or not conversation.pending_quote):
            raise NoPendingQuote()

        with conversation.lock:
            reply = chat_pattern.reply(conversation.id, customer_id, message_for_action(action, message))
            if chat_pattern.supports_quotes:
                conversation.pending_quote = reply.pending_quote
        return ChatTurn(conversation_id=conversation.id, pattern=pattern, reply=reply)
