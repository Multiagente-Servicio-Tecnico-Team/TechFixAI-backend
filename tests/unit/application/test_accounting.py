from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.accounting import AccountingService
from app.application.errors import AccountingConflict, AccountingNotFound
from app.domain.accounting import AccountingValidationError, EntryDraft, EntryLine


class FakeRepository:
    def __init__(self):
        self.calls = []

    def list_categories(self):
        return [{"id": 1, "code": "SALE", "name": "Venta", "description": None}]

    def create_entry(self, actor_id, idempotency_key, request_hash, draft):
        self.calls.append((actor_id, idempotency_key, request_hash, draft))
        return ({"id": 1, "entry_number": 1}, False)

    def list_entries(self, **filters):
        return {"items": [], "total": 0, "limit": filters["limit"], "offset": filters["offset"]}

    def get_entry(self, entry_id):
        return None

    def reverse_entry(self, actor_id, entry_id, operation_date, reason):
        return None


def test_create_uses_session_actor_and_stable_hash():
    repo = FakeRepository()
    service = AccountingService(repo)
    draft = EntryDraft(date(2026, 11, 2), "Venta", "Detalle", 1, (
        EntryLine("1", "Debe", None, Decimal("2.00"), Decimal("0.00")),
        EntryLine("2", "Haber", None, Decimal("0.00"), Decimal("2.00")),
    ))
    key = UUID("723d06c0-65da-4d2c-8471-b8d71d28771c")
    service.create_entry(actor_id=8, idempotency_key=key, draft=draft)
    assert repo.calls[0][0] == 8
    assert repo.calls[0][1] == key
    assert len(repo.calls[0][2]) == 64


def test_detail_missing_raises_safe_not_found():
    with pytest.raises(AccountingNotFound):
        AccountingService(FakeRepository()).get_entry(99)


def test_request_hash_is_canonical():
    assert AccountingService.canonical_hash({"a": 1, "b": 2}) == AccountingService.canonical_hash({"b": 2, "a": 1})


@pytest.mark.parametrize("reason", ["", " " * 2, "x" * 2001])
def test_reversal_reason_is_required_and_limited(reason):
    with pytest.raises(AccountingValidationError):
        AccountingService(FakeRepository()).reverse_entry(
            actor_id=8, entry_id=1, operation_date=date(2026, 11, 3), reason=reason
        )


def test_conflict_from_repository_is_preserved_for_already_reversed_entry():
    class ReversedRepository(FakeRepository):
        def reverse_entry(self, *_args):
            raise AccountingConflict()

    with pytest.raises(AccountingConflict):
        AccountingService(ReversedRepository()).reverse_entry(
            actor_id=8, entry_id=1, operation_date=date(2026, 11, 3), reason="Correction"
        )
