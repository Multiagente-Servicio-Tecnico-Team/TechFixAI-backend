from decimal import Decimal

from app.agents.jerarquico.sales import make_sales_agent
from app.settings import Settings


def settings():
    return Settings(
        groq_api_key=None,
        groq_model=None,
        database_url=None,
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("35.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )


def current_quote():
    return {
        "id": 4,
        "code": "SSD-512",
        "name": "SSD NVMe 512GB",
        "quantity": 1,
        "unit_price": Decimal("44.90"),
        "current_stock": 4,
    }


def test_sales_agent_requires_new_confirmation_after_live_quote_changes():
    class DirectQuotes:
        def __init__(self):
            self.created = []
            self.resolved = []

        def create_direct_sales_quote(self, **kwargs):
            self.created.append(kwargs)
            return {"id": 101}

        def resolve_direct_sales_quote(self, **kwargs):
            self.resolved.append(kwargs)

    quotes = DirectQuotes()
    state = {
        "customer_id": 9,
        "quote_id": 100,
        "request_type": "SALE",
        "route": "confirm",
        "matched_parts": [current_quote()],
        "quote": {
            "quote_type": "DIRECT_SALE",
            "labor_task_type": "sale",
            "labor_cost": Decimal("0.00"),
            "parts_cost": Decimal("39.90"),
            "total_amount": Decimal("39.90"),
            "parts": [{**current_quote(), "unit_price": Decimal("39.90"),
                       "subtotal": Decimal("39.90")}],
        },
    }

    result = make_sales_agent(settings(), direct_sales_quotes=quotes)(state)

    assert result["outcome"] == "price_changed"
    assert result["route"] == "service"
    assert result["quote_changed"] is True
    assert result["quote"]["total_amount"] == Decimal("44.90")
    assert result["quote_id"] == 101
    assert quotes.resolved[0]["target_status"] == "CANCELLED"


def test_sales_agent_keeps_matching_quote_confirmable():
    class DirectQuotes:
        def create_direct_sales_quote(self, **kwargs):
            return {"id": 101}

    state = {
        "customer_id": 9,
        "request_type": "SALE",
        "route": "confirm",
        "matched_parts": [current_quote()],
    }
    initial = make_sales_agent(settings(), direct_sales_quotes=DirectQuotes())(state)
    state["quote"] = initial["quote"]
    state["quote_id"] = initial["quote_id"]

    result = make_sales_agent(settings(), direct_sales_quotes=DirectQuotes())(state)

    assert result.get("outcome") is None
    assert result.get("quote_changed") is None
