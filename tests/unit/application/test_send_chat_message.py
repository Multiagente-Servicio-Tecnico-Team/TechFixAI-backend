"""Caso de uso del chat con dobles de prueba: sin FastAPI, LangGraph ni base de datos."""
import pytest

from app.application.chat import SendChatMessage
from app.application.conversations import ConversationRegistry
from app.application.errors import RateLimited
from app.application.ports import ChatPattern
from app.application.tickets import ListCustomerTickets
from app.domain.chat import ACTION_MESSAGES, PatternReply, Quote
from app.domain.errors import ConversationNotFound, NoPendingQuote, PatternLocked
from app.domain.tickets import CustomerTicket

PROPOSED = Quote(status="proposed", lines=[], total="50")


class FakePattern:
    def __init__(self, pattern_id, replies=None, supports_quotes=True):
        self.id = pattern_id
        self.name = pattern_id
        self.supports_quotes = supports_quotes
        self.replies = list(replies or [])
        self.calls = []

    def reply(self, conversation_id, customer_id, message):
        self.calls.append((conversation_id, customer_id, message))
        return self.replies.pop(0) if self.replies else PatternReply(reply="ok")


class FakeLimiter:
    def __init__(self, limit=100):
        self.limit = limit
        self.count = {}

    def blocked(self, key):
        return self.count.get(key, 0) >= self.limit

    def fail(self, key):
        self.count[key] = self.count.get(key, 0) + 1


def use_case(*patterns, limiter=None):
    return SendChatMessage({p.id: p for p in patterns}, ConversationRegistry(), limiter or FakeLimiter())


def test_fake_pattern_satisfies_the_port():
    assert isinstance(FakePattern("hierarchical"), ChatPattern)


def test_first_message_opens_a_conversation_and_reuses_it():
    pattern = FakePattern("hierarchical")
    chat = use_case(pattern)

    first = chat.execute(customer_id=7, pattern="hierarchical", message="Hola")
    second = chat.execute(customer_id=7, pattern="hierarchical", message="Sigo", conversation_id=first.conversation_id)

    assert first.conversation_id == second.conversation_id
    assert [call[2] for call in pattern.calls] == ["Hola", "Sigo"]
    assert pattern.calls[0][:2] == (first.conversation_id, 7)


def test_conversation_of_another_customer_is_not_found():
    chat = use_case(FakePattern("hierarchical"))
    turn = chat.execute(customer_id=1, pattern="hierarchical", message="Hola")

    with pytest.raises(ConversationNotFound):
        chat.execute(customer_id=2, pattern="hierarchical", message="x", conversation_id=turn.conversation_id)
    with pytest.raises(ConversationNotFound):
        chat.execute(customer_id=1, pattern="hierarchical", message="x", conversation_id="no-existe")


def test_pattern_cannot_change_inside_a_conversation():
    chat = use_case(FakePattern("hierarchical"), FakePattern("orchestrator"))
    turn = chat.execute(customer_id=1, pattern="hierarchical", message="Hola")

    with pytest.raises(PatternLocked):
        chat.execute(customer_id=1, pattern="orchestrator", message="x", conversation_id=turn.conversation_id)


def test_buttons_only_work_with_a_pending_quote():
    pattern = FakePattern("orchestrator", [PatternReply(reply="Presupuesto", quote=PROPOSED, pending_quote=True)])
    chat = use_case(pattern)

    with pytest.raises(NoPendingQuote):
        chat.execute(customer_id=1, pattern="orchestrator", action="accept_quote")

    turn = chat.execute(customer_id=1, pattern="orchestrator", message="Cotiza")
    chat.execute(customer_id=1, pattern="orchestrator", action="reject_quote", conversation_id=turn.conversation_id)

    assert pattern.calls[-1][2] == ACTION_MESSAGES["reject_quote"]
    # El rechazo devolvió una respuesta sin presupuesto pendiente: otro clic ya no aplica.
    with pytest.raises(NoPendingQuote):
        chat.execute(customer_id=1, pattern="orchestrator", action="accept_quote", conversation_id=turn.conversation_id)


def test_patterns_without_quotes_reject_buttons():
    pattern = FakePattern("decentralized", [PatternReply(reply="x", pending_quote=True)], supports_quotes=False)
    chat = use_case(pattern)
    turn = chat.execute(customer_id=1, pattern="decentralized", message="Hola")

    with pytest.raises(NoPendingQuote):
        chat.execute(customer_id=1, pattern="decentralized", action="accept_quote", conversation_id=turn.conversation_id)


def test_rate_limit_counts_every_message_of_the_customer():
    chat = use_case(FakePattern("hierarchical"), limiter=FakeLimiter(limit=2))
    chat.execute(customer_id=1, pattern="hierarchical", message="1")
    chat.execute(customer_id=1, pattern="hierarchical", message="2")

    with pytest.raises(RateLimited):
        chat.execute(customer_id=1, pattern="hierarchical", message="3")
    chat.execute(customer_id=2, pattern="hierarchical", message="otro cliente")


def test_list_tickets_asks_the_reader_for_the_session_customer():
    seen = []

    class Reader:
        def list_for_customer(self, customer_id):
            seen.append(customer_id)
            return [CustomerTicket("TCK-1", "Laptop", "No enciende", "REPAIR", "NEW")]

    tickets = ListCustomerTickets(Reader).execute(42)

    assert seen == [42]
    assert tickets[0].code == "TCK-1"
