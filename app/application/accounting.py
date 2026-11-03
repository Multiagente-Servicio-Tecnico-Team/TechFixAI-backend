"""Casos de uso contables, desacoplados de FastAPI y PostgreSQL."""
import hashlib
import json
from datetime import date
from uuid import UUID

from app.application.errors import AccountingNotFound
from app.domain.accounting import AccountingValidationError, EntryDraft, validate_draft


class AccountingService:
    def __init__(self, repository):
        self.repository = repository

    def list_categories(self):
        return self.repository.list_categories()

    @staticmethod
    def _canonical_payload(draft: EntryDraft) -> dict[str, object]:
        return {
            "operation_date": draft.operation_date.isoformat(),
            "concept": draft.concept,
            "detail": draft.detail,
            "category_id": draft.category_id,
            "lines": [
                {
                    "account_code": line.account_code,
                    "account_name": line.account_name,
                    "description": line.description,
                    "debit": format(line.debit, ".2f"),
                    "credit": format(line.credit, ".2f"),
                }
                for line in draft.lines
            ],
        }

    @staticmethod
    def canonical_hash(payload: dict[str, object]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def create_entry(self, *, actor_id: int, idempotency_key: UUID, draft: EntryDraft):
        if actor_id < 1:
            raise AccountingValidationError("El actor autenticado no es válido.")
        validated = validate_draft(draft)
        digest = self.canonical_hash(self._canonical_payload(validated.draft))
        return self.repository.create_entry(actor_id, idempotency_key, digest, validated)

    def list_entries(self, **filters):
        return self.repository.list_entries(**filters)

    def get_entry(self, entry_id: int):
        entry = self.repository.get_entry(entry_id)
        if entry is None:
            raise AccountingNotFound()
        return entry

    def reverse_entry(self, *, actor_id: int, entry_id: int, operation_date: date, reason: str):
        if actor_id < 1:
            raise AccountingValidationError("El actor autenticado no es válido.")
        normalized_reason = reason.strip()
        if not 1 <= len(normalized_reason) <= 2000:
            raise AccountingValidationError("La razón debe tener entre 1 y 2000 caracteres.")
        return self.repository.reverse_entry(actor_id, entry_id, operation_date, normalized_reason)
