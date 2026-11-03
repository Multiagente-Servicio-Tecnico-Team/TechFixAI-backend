from decimal import Decimal

import pytest

from app.application.ports import (
    CatalogItem,
    CatalogMatch,
    KnowledgeFilters,
    LogisticsPreference,
    QuoteDraft,
    QuoteLineDraft,
    RefundRequestDraft,
    RetrievedPassage,
    WarrantyRecord,
)


def test_catalog_service_delegates_lookup_and_candidate_search_to_repository():
    from app.application.catalog import CatalogService

    class CatalogRepository:
        def lookup_inventory(self, name, quantity):
            return {
                "name": name,
                "quantity": quantity,
                "stock": 4,
                "unit_price": "125.00",
                "available": quantity <= 4,
            }

        def find_spare_parts(self, term):
            return [{"code": term}]

        def find_catalog_items(self, term, *, limit=20):
            return [{"code": term, "limit": limit}]

        def find_spare_part_by_code(self, code):
            return {"code": code}

        def find_spare_part_alternatives(self, term):
            return [{"code": f"alternative:{term}"}]

    service = CatalogService(CatalogRepository())

    assert service.lookup("SSD", 2)["unit_price"] == "125.00"
    assert service.find_spare_parts("RAM")[0]["code"] == "RAM"
    assert service.find_catalog_items("SSD", limit=8)[0]["limit"] == 8
    assert service.find_by_code("SSD-1")["code"] == "SSD-1"
    assert service.find_alternatives("battery")[0]["code"] == "alternative:battery"


def test_quote_acceptance_recalculates_totals_before_repository_write():
    from app.application.quotes import accept_quoted_draft, calculate_quote
    from app.domain.errors import StaleQuote

    class Writer:
        def __init__(self):
            self.calls = []

        def accept_ticket_quote(self, **values):
            self.calls.append(values)
            return {"quote_id": 19, "payment_id": 23}

    writer = Writer()
    valid = {
        **calculate_quote(
            labor_cost=Decimal("35.00"),
            labor_task_type="maintenance",
            parts=[{"id": 4, "code": "SSD-512", "quantity": 1,
                    "unit_price": Decimal("44.90"), "current_stock": 3}],
        ),
        "quote_type": "REPAIR",
    }

    result = accept_quoted_draft(
        writer=writer, customer_id=41, ticket_id=10, quote_type="REPAIR",
        draft=valid, observations="confirmación explícita", payment_code="PAY-TEST",
    )

    assert result["quote_id"] == 19
    assert writer.calls[0]["total_amount"] == Decimal("79.90")
    assert writer.calls[0]["customer_id"] == 41

    forged_total = {**valid, "total_amount": Decimal("0.01")}
    with pytest.raises(StaleQuote):
        accept_quoted_draft(
            writer=writer, customer_id=41, ticket_id=10, quote_type="REPAIR",
            draft=forged_total, observations="confirmación explícita", payment_code="PAY-TEST",
        )
    assert len(writer.calls) == 1


def test_shared_capability_result_types_preserve_business_values():
    item = CatalogItem(3, "SSD-512", "SSD 512GB", "Almacenamiento", Decimal("49.90"), 4, True)
    match = CatalogMatch("ssd 512", "exact", (item,))
    quote = QuoteDraft(
        ticket_id=8,
        quote_type="REPAIR",
        labor_task_type="maintenance",
        labor_cost=Decimal("35.00"),
        parts_cost=Decimal("49.90"),
        total_amount=Decimal("84.90"),
        currency="PEN",
        lines=(QuoteLineDraft(3, 1, item.unit_price, item.unit_price),),
    )
    refund = RefundRequestDraft(6, 12, Decimal("84.90"), "Falla del producto")
    logistics = LogisticsPreference(8, 12, "COURIER_SHIPMENT", 5)
    warranty = WarrantyRecord(2, "WAR-02", 12, "ACTIVE", 8)
    passage = RetrievedPassage(
        "Guía técnica", "manual.thermal", "manual.md", "Temperatura", "digest",
        "verified_guide", 0.82, "semantic",
    )

    assert match.items[0].current_stock >= 1
    assert quote.total_amount == quote.labor_cost + quote.parts_cost
    assert refund.customer_id == logistics.customer_id == warranty.customer_id
    assert passage.trust_level == "verified_guide"
    assert KnowledgeFilters(trust_levels=frozenset({"verified_guide"})).trust_levels
