"""Casos de uso de consulta y administración del inventario."""
from app.application.errors import InventoryNotFound, InventoryValidationError
from app.application.ports import InventoryRepository
from app.domain.errors import InventoryValidationFailure
from app.domain.inventory import InventoryPartDraft, movement_type_for_delta, validate_inventory_part, validate_movement_reason, validate_stock_count


class InventoryService:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def list_parts(self):
        return self.repository.list_parts()

    def list_categories(self):
        return self.repository.list_categories()

    @staticmethod
    def _validate(values: dict[str, object]) -> InventoryPartDraft:
        try:
            return validate_inventory_part(values)
        except InventoryValidationFailure as exc:
            raise InventoryValidationError(str(exc), field=exc.field) from exc

    def create_part(self, values: dict[str, object], *, actor_id: int):
        draft = self._validate(values)
        return self.repository.create_part(draft, actor_id=actor_id)

    def update_part(self, code: str, values: dict[str, object], *, actor_id: int):
        draft = self._validate(values)
        if draft.code != code:
            raise InventoryValidationError("El código no se puede cambiar durante la edición.", field="code")
        part = self.repository.update_part(code, draft, actor_id=actor_id)
        if part is None:
            raise InventoryNotFound()
        return part

    def delete_part(self, code: str):
        if not self.repository.delete_part(code):
            raise InventoryNotFound()

    def record_opening_balance(self, *, part_id: int, count: object, actor_id: int, reason: object, idempotency_key, request_hash: str):
        return self.repository.record_opening_balance(part_id=part_id, count=self._count(count), actor_id=actor_id,
            reason=self._reason(reason), idempotency_key=idempotency_key, request_hash=request_hash)

    def adjust_stock(self, *, part_id: int, count: object, actor_id: int, reason: object, idempotency_key, request_hash: str):
        return self.repository.adjust_stock(part_id=part_id, count=self._count(count), actor_id=actor_id,
            reason=self._reason(reason), idempotency_key=idempotency_key, request_hash=request_hash)

    def list_movements(self, **filters):
        return self.repository.list_movements(**filters)

    @staticmethod
    def _count(value):
        try:
            return validate_stock_count(value)
        except InventoryValidationFailure as exc:
            raise InventoryValidationError(str(exc), field=exc.field) from exc

    @staticmethod
    def _reason(value):
        try:
            return validate_movement_reason(value)
        except InventoryValidationFailure as exc:
            raise InventoryValidationError(str(exc), field=exc.field) from exc

    @staticmethod
    def movement_type_for_delta(delta: int) -> str:
        try:
            return movement_type_for_delta(delta)
        except InventoryValidationFailure as exc:
            raise InventoryValidationError(str(exc), field=exc.field) from exc
