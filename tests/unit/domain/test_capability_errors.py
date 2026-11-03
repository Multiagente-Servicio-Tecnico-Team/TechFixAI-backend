from app.application.errors import (
    AmbiguousCatalogFailure,
    InsufficientStockFailure,
    KnowledgeUnavailableFailure,
    OwnershipFailure,
    RefundEligibilityFailure,
    StaleQuoteFailure,
)
from app.domain.errors import (
    AmbiguousCatalogMatch,
    InsufficientStock,
    KnowledgeUnavailable,
    OwnershipViolation,
    StaleQuote,
)
from app.domain.refunds import RefundEligibilityError


def test_domain_and_application_errors_expose_stable_codes_and_safe_details():
    pairs = (
        (AmbiguousCatalogMatch, AmbiguousCatalogFailure, "catalog_ambiguous"),
        (InsufficientStock, InsufficientStockFailure, "insufficient_stock"),
        (StaleQuote, StaleQuoteFailure, "stale_quote"),
        (OwnershipViolation, OwnershipFailure, "ownership_violation"),
        (RefundEligibilityError, RefundEligibilityFailure, "refund_ineligible"),
        (KnowledgeUnavailable, KnowledgeUnavailableFailure, "knowledge_unavailable"),
    )
    for domain_error, application_error, expected_code in pairs:
        assert domain_error.code == expected_code
        assert application_error.code == expected_code
        assert "secret" not in domain_error.detail.casefold()
        assert "secret" not in application_error.detail.casefold()
