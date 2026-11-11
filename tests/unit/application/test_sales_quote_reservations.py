from datetime import UTC, datetime, timedelta

import pytest

from app.application.sales_quotes import AcceptDirectSalesQuote, validate_direct_sale_acceptance


def test_acceptance_requires_pending_quote_and_future_timezone_aware_expiry():
    now = datetime.now(UTC)
    quote = {"id": 1, "kind": "DIRECT_SALE", "status": "PENDING", "expires_at": now + timedelta(minutes=5)}
    assert validate_direct_sale_acceptance(quote, now=now) == 1

    with pytest.raises(ValueError, match="pendiente"):
        validate_direct_sale_acceptance({**quote, "status": "ACCEPTED"}, now=now)
    with pytest.raises(ValueError, match="futura"):
        validate_direct_sale_acceptance({**quote, "expires_at": now}, now=now)
    with pytest.raises(ValueError, match="zona horaria"):
        validate_direct_sale_acceptance({**quote, "expires_at": now.replace(tzinfo=None)}, now=now)


def test_acceptance_refuses_service_quote_and_invalid_identity():
    now = datetime.now(UTC)
    quote = {"id": 1, "kind": "REPAIR", "status": "PENDING", "expires_at": now + timedelta(minutes=5)}
    with pytest.raises(ValueError, match="venta directa"):
        validate_direct_sale_acceptance(quote, now=now)
    with pytest.raises(ValueError, match="identificador"):
        validate_direct_sale_acceptance({**quote, "kind": "DIRECT_SALE"}, now=now, customer_id=0)


def test_acceptance_use_case_passes_identity_and_idempotency_key_to_writer():
    calls = []

    class Writer:
        def accept_direct_sales_quote(self, **values):
            calls.append(values)
            return {"quote_id": values["quote_id"], "status": "ACCEPTED"}

    use_case = AcceptDirectSalesQuote(lambda: Writer())
    result = use_case.execute(
        quote_id=12, customer_id=7, actor_user_id=7,
        idempotency_key=" accept-12 ",
    )
    assert result == {"quote_id": 12, "status": "ACCEPTED"}
    assert calls == [{
        "quote_id": 12, "customer_id": 7, "actor_user_id": 7,
        "idempotency_key": "accept-12",
    }]
