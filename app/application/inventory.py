"""Casos de uso de consulta y administración del inventario."""
from app.application.errors import InventoryNotFound, InventoryValidationError
from app.application.ports import InventoryRepository
from app.domain.errors import InventoryValidationFailure
from app.domain.inventory import InventoryPartDraft, validate_inventory_part


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

    def create_part(self, values: dict[str, object]):
        draft = self._validate(values)
        return self.repository.create_part(draft)

    def update_part(self, code: str, values: dict[str, object]):
        draft = self._validate(values)
        if draft.code != code:
            raise InventoryValidationError("El código no se puede cambiar durante la edición.", field="code")
        part = self.repository.update_part(code, draft)
        if part is None:
            raise InventoryNotFound()
        return part

    def delete_part(self, code: str):
        if not self.repository.delete_part(code):
            raise InventoryNotFound()
