from decimal import Decimal

import pytest

from app.domain.chat import ACTION_MESSAGES, PatternReply, Quote, QuoteLine, message_for_action
from app.domain.money import money_text, to_money
from app.domain.tickets import TicketQuote, TicketQuoteLine


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("35"), "35.00"), (180, "180.00"), ("215.5", "215.50"), ("180.005", "180.01"), (0, "0.00")],
)
def test_money_uses_decimal_with_two_places(value, expected):
    assert money_text(value) == expected
    assert isinstance(to_money(value), Decimal)


def test_quote_normalizes_amounts_and_knows_when_it_is_pending():
    quote = Quote(status="proposed", lines=[QuoteLine("Mano de obra", 35), QuoteLine("SSD × 1", "180")], total="215")

    assert quote.total == Decimal("215.00")
    assert [line.amount for line in quote.lines] == [Decimal("35.00"), Decimal("180.00")]
    assert quote.currency == "PEN"
    assert quote.is_pending
    assert not Quote(status="saved", lines=[], total=0).is_pending


def test_buttons_become_messages_the_patterns_understand():
    assert message_for_action("accept_quote", None) == ACTION_MESSAGES["accept_quote"]
    assert message_for_action("reject_quote", "ignorado") == ACTION_MESSAGES["reject_quote"]
    assert message_for_action(None, "Mi laptop no enciende") == "Mi laptop no enciende"
    assert message_for_action(None, None) == ""


def test_reply_defaults_to_no_quote_and_no_ticket():
    reply = PatternReply(reply="Hola")
    assert (reply.quote, reply.ticket, reply.pending_quote) == (None, None, False)


def test_ticket_quote_keeps_missing_amounts_as_none():
    quote = TicketQuote(
        status="PENDING",
        labor_cost=None,
        parts_cost="180",
        total_amount=Decimal("215"),
        created_at=None,
        lines=[TicketQuoteLine("SSD", "1", 180, "180.00")],
    )
    assert quote.labor_cost is None
    assert quote.parts_cost == Decimal("180.00")
    assert quote.lines[0].quantity == 1
