from decimal import Decimal
import pytest

from app.domain.ticket_management import ADVANCE_METHODS, REQUEST_TYPES, TICKET_STATUSES, money


def test_money_uses_exact_decimal_and_rejects_non_positive_values():
    assert money("12.30") == Decimal("12.30")
    with pytest.raises(ValueError):
        money("0")


def test_canonical_ticket_values_match_schema():
    assert REQUEST_TYPES == {"REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"}
    assert "CANCELLED" in TICKET_STATUSES
    assert ADVANCE_METHODS == {"YAPE_PLIN", "CASH", "CARD"}
