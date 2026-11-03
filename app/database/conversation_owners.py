"""Technical ownership only. Caller supplies identity from authenticated session.

Inject CheckpointResources.pool; this repository never opens/closes the pool,
creates tables, or reads credentials. All SQL targets the fixed technical schema.
"""


class ConversationConflict(ValueError):
    """An identifier is already bound to different immutable data."""


class ConversationNotFound(LookupError):
    """Same response for unknown and other-customer conversations."""


class ConversationStorageError(RuntimeError):
    """Storage failure without driver details or credentials."""


def _identifier(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Identificador de conversación obligatorio")
    # TEXT has no SQL length limit; preserve exact identifiers, no silent strip.
    return value


def _customer(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValueError("Identidad autenticada inválida")
    return value


def _pattern(value):
    if value != "decentralized":
        raise ConversationConflict("Patrón incompatible")
    return value


class ConversationOwnersRepository:
    def __init__(self, pool):
        self.pool = pool

    def register(self, *, conversation_id, thread_id, authenticated_customer_id,
                 pattern="decentralized"):
        """Exact retries return existing owner; all other collisions fail closed."""
        conversation_id = _identifier(conversation_id)
        thread_id = _identifier(thread_id)
        customer_id = _customer(authenticated_customer_id)
        pattern = _pattern(pattern)
        try:
            with self.pool.connection() as conn:
                with conn.transaction():
                    row = conn.execute("""INSERT INTO langgraph_decentralized.conversation_owners
                        (conversation_id, thread_id, customer_id, pattern)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT DO NOTHING RETURNING *""",
                        (conversation_id, thread_id, customer_id, pattern)).fetchone()
                    if row is None:
                        row = conn.execute("""SELECT * FROM langgraph_decentralized.conversation_owners
                            WHERE conversation_id=%s""", (conversation_id,)).fetchone()
                        if (row is None or row["thread_id"] != thread_id
                                or row["customer_id"] != customer_id or row["pattern"] != pattern):
                            raise ConversationConflict("Identificador de conversación o thread ya utilizado")
                    return dict(row)
        except ConversationConflict:
            raise
        except Exception:
            raise ConversationStorageError("No fue posible registrar la conversación") from None

    def authorize(self, *, conversation_id, authenticated_customer_id,
                  pattern="decentralized"):
        conversation_id = _identifier(conversation_id)
        customer_id = _customer(authenticated_customer_id)
        pattern = _pattern(pattern)
        try:
            with self.pool.connection() as conn:
                with conn.transaction():
                    row = conn.execute("""SELECT * FROM langgraph_decentralized.conversation_owners
                        WHERE conversation_id=%s AND customer_id=%s""",
                        (conversation_id, customer_id)).fetchone()
                    if row is None:
                        raise ConversationNotFound("Conversación no encontrada")
                    if row["pattern"] != pattern:
                        raise ConversationConflict("Patrón incompatible")
                    return dict(row)
        except (ConversationNotFound, ConversationConflict):
            raise
        except Exception:
            raise ConversationStorageError("No fue posible consultar la conversación") from None

    def touch(self, *, conversation_id, authenticated_customer_id,
              pattern="decentralized"):
        """Atomically authorize and update activity; immutable fields never change."""
        conversation_id = _identifier(conversation_id)
        customer_id = _customer(authenticated_customer_id)
        pattern = _pattern(pattern)
        try:
            with self.pool.connection() as conn:
                with conn.transaction():
                    row = conn.execute("""SELECT * FROM langgraph_decentralized.conversation_owners
                        WHERE conversation_id=%s AND customer_id=%s FOR UPDATE""",
                        (conversation_id, customer_id)).fetchone()
                    if row is None:
                        raise ConversationNotFound("Conversación no encontrada")
                    if row["pattern"] != pattern:
                        raise ConversationConflict("Patrón incompatible")
                    updated = conn.execute("""UPDATE langgraph_decentralized.conversation_owners
                        SET updated_at=CURRENT_TIMESTAMP
                        WHERE conversation_id=%s AND customer_id=%s AND pattern=%s RETURNING *""",
                        (conversation_id, customer_id, pattern)).fetchone()
                    if updated is None:
                        raise ConversationStorageError("No se actualizó la actividad")
                    return dict(updated)
        except (ConversationNotFound, ConversationConflict, ConversationStorageError):
            raise
        except Exception:
            raise ConversationStorageError("No fue posible actualizar la actividad") from None
