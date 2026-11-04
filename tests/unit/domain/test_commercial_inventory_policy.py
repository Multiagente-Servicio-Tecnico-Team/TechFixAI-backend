import pytest

from app.domain.customer_commerce import available_stock


def test_available_stock_subtracts_all_active_reservations():
    assert available_stock(12, 5) == 7
    assert available_stock(12, 12) == 0


@pytest.mark.parametrize(
    ("current", "reserved"),
    [(-1, 0), (4, -1), (3, 4), (True, 0), (4, False)],
)
def test_available_stock_rejects_invalid_or_overreserved_balances(current, reserved):
    with pytest.raises(ValueError):
        available_stock(current, reserved)
