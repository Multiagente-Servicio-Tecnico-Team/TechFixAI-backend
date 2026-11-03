"""Durable ownership and coordination adapter for both text and audio turns."""
import logging
from uuid import uuid4
from types import SimpleNamespace
from sqlalchemy.exc import SQLAlchemyError
from groq import APIError as GroqAPIError
from app.application.errors import ConversationActionError, StorageUnavailable, PatternFailure
from app.domain.errors import ConversationNotFound, PatternLocked
from app.database.conversation_owners import ConversationNotFound as MissingOwner, ConversationConflict, ConversationStorageError
from app.database.conversation_locks import ConversationBusy, ConversationLockStorageError
logger = logging.getLogger(__name__)


class DurableConversations:
    def __init__(self, app, pattern, registry, owners=None, locks=None):
        self.app, self.pattern, self.registry = app, pattern, registry
        self.owners, self.locks = owners, locks

    def check_other_pattern(self, conversation_id, customer_id):
        # Un ID desconocido lo rechaza el registro del patron solicitado sin SQL.
        # El descentralizado siempre autoriza contra su almacenamiento en execute().
        if conversation_id and self.registry.known_pattern(conversation_id, customer_id) == "decentralized":
            raise PatternLocked()

    def execute(self, *, customer_id, message, conversation_id=None, action=None, proposal_id=None):
        if conversation_id and self.registry.known_pattern(conversation_id, customer_id) not in {None, "decentralized"}:
            raise PatternLocked()
        owners = self.owners or self.app.state.conversation_owners
        locks = self.locks or self.app.state.conversation_locks
        if owners is None or locks is None:
            raise StorageUnavailable("El almacenamiento durable del asistente no esta disponible.")
        new = conversation_id is None
        conversation_id = conversation_id or str(uuid4())
        try:
            if new:
                owner = owners.register(conversation_id=conversation_id, thread_id=conversation_id,
                                        authenticated_customer_id=customer_id)
            else:
                owner = owners.authorize(conversation_id=conversation_id, authenticated_customer_id=customer_id)
        except MissingOwner:
            raise ConversationNotFound() from None
        except ConversationConflict:
            raise PatternLocked() from None
        except ConversationStorageError:
            raise StorageUnavailable() from None
        self.registry.remember(conversation_id, customer_id, "decentralized")
        try:
            with locks.hold(owner["thread_id"]):
                result = self.pattern.invoke_turn("decentralized", conversation_id, SimpleNamespace(id=customer_id),
                    message or "", thread_id=owner["thread_id"],
                    resume_payment=action == "resume_payment", resume_logistics=action == "resume_logistics",
                    resume_warranty=action == "resume_warranty",
                    quote_action=action if action in {"accept_quote", "reject_quote"} else None,
                    proposal_id=proposal_id)
                return conversation_id, self.pattern.to_reply(result)
        except ConversationBusy:
            raise ConversationActionError(409, "La conversacion esta procesando otro mensaje.", "conversation_busy") from None
        except (ConversationLockStorageError, SQLAlchemyError, OSError) as exc:
            logger.error("Decentralized storage failed: %s", type(exc).__name__)
            raise StorageUnavailable() from None
        except GroqAPIError:
            raise PatternFailure("llm") from None
        except ConversationActionError:
            raise
        except (ValueError, LookupError, RuntimeError) as exc:
            logger.error("Decentralized processing failed: %s", type(exc).__name__)
            raise PatternFailure("pattern") from None
