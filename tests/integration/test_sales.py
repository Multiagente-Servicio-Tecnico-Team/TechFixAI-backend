from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.agents.sales import DEMO_REQUEST, QuoteRequest, build_sales_graph


def test_demo_quote():
    quote = build_sales_graph().invoke({"request": DEMO_REQUEST})["quote"]
    assert quote["status"] == "ready"
    assert quote["labor_subtotal"] == "80.00"
    assert quote["parts_subtotal"] == "180.00"
    assert quote["total"] == "260.00"
    assert sum(Decimal(i["amount"]) for i in quote["labor"] + quote["parts"]) == Decimal(quote["total"])


def test_missing_and_unknown():
    quote = build_sales_graph().invoke({"request": {"items": [{"code": "unknown"}]}})["quote"]
    assert quote["total"] is None
    assert len(quote["missing_data"]) == 3


def test_quantity_and_empty():
    quote = build_sales_graph().invoke({"request": {"items": [{"code": "revision", "quantity": 3}]}})["quote"]
    assert quote["known_subtotal"] == "150.00"
    assert len(build_sales_graph().invoke({"request": {}})["quote"]["missing_data"]) == 3
    for quantity in [0, -1, 1.5, True, 1001]:
        with pytest.raises(ValidationError):
            QuoteRequest(items=[{"code": "revision", "quantity": quantity}])
