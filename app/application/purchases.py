"""Casos de uso para compras internas a proveedores."""
import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping
from uuid import UUID

from app.application.errors import PurchaseConflict, PurchaseNotFound, PurchaseError, SupplierNotFound
from app.application.ports import SupplierPurchaseRepository
from app.domain.purchases import PurchaseValidationFailure, validate_purchase, validate_supplier


def _as_error(exc: PurchaseValidationFailure) -> PurchaseError:
    return PurchaseError(str(exc), field=exc.field)


class SupplierPurchaseService:
    def __init__(self, repository: SupplierPurchaseRepository):
        self.repository = repository

    def list_suppliers(self, *, active: bool | None, search: str | None, limit: int, offset: int):
        return self.repository.list_suppliers(active=active, search=search, limit=limit, offset=offset)

    def get_supplier(self, supplier_id: int):
        if supplier_id < 1:
            raise PurchaseError("El identificador de proveedor no es válido.", field="supplier_id")
        supplier = self.repository.get_supplier(supplier_id)
        if supplier is None:
            raise SupplierNotFound()
        return supplier

    def create_supplier(self, values: Mapping[str, object]):
        try:
            return self.repository.create_supplier(validate_supplier(values))
        except PurchaseValidationFailure as exc:
            raise _as_error(exc) from exc

    def update_supplier(self, supplier_id: int, values: Mapping[str, object]):
        if supplier_id < 1:
            raise PurchaseError("El identificador de proveedor no es válido.", field="supplier_id")
        try:
            validated = validate_supplier(values, partial=True)
            if not validated:
                raise PurchaseValidationFailure("Indica al menos un campo para actualizar.")
            supplier = self.repository.update_supplier(supplier_id, validated)
        except PurchaseValidationFailure as exc:
            raise _as_error(exc) from exc
        if supplier is None:
            raise SupplierNotFound()
        return supplier

    def create_purchase(self, *, actor_id: int, values: Mapping[str, object]):
        try:
            draft = validate_purchase(values)
            return self.repository.create_purchase(actor_id=actor_id, draft=draft, values=dict(values))
        except PurchaseValidationFailure as exc:
            raise _as_error(exc) from exc

    def get_purchase(self, purchase_id: int):
        if purchase_id < 1:
            raise PurchaseError("El identificador de compra no es válido.", field="purchase_id")
        purchase = self.repository.get_purchase(purchase_id)
        if purchase is None:
            raise PurchaseNotFound()
        return purchase

    def list_purchases(self, *, supplier_id: int | None, from_date: date | None, to_date: date | None,
                       status: str | None, payment_status: str | None, document_number: str | None,
                       limit: int, offset: int):
        if supplier_id is not None and supplier_id < 1:
            raise PurchaseError("El identificador de proveedor no es válido.", field="supplier_id")
        if from_date and to_date and from_date > to_date:
            raise PurchaseError("El rango de fechas no es válido.", field="from_date")
        if status is not None and status not in {"REGISTERED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"}:
            raise PurchaseError("El estado de compra no es válido.", field="status")
        if payment_status is not None and payment_status not in {"PENDING", "PAID"}:
            raise PurchaseError("El estado de pago no es válido.", field="payment_status")
        if not 1 <= limit <= 100 or offset < 0:
            raise PurchaseError("La paginación no es válida.", field="limit")
        return self.repository.list_purchases(supplier_id=supplier_id, from_date=from_date, to_date=to_date,
                                              status=status, payment_status=payment_status,
                                              document_number=document_number, limit=limit, offset=offset)

    def update_purchase(self, *, actor_id: int, purchase_id: int, values: Mapping[str, object]):
        if purchase_id < 1 or not values or set(values) - {"payment_status", "notes"}:
            raise PurchaseError("Los campos de actualización no son válidos.")
        if "payment_status" in values and values["payment_status"] not in ("PENDING", "PAID"):
            raise PurchaseError("El estado de pago no es válido.", field="payment_status")
        try:
            purchase = self.repository.update_purchase(actor_id=actor_id, purchase_id=purchase_id, values=dict(values))
        except PurchaseConflict:
            raise
        if purchase is None:
            raise PurchaseNotFound()
        return purchase

    def cancel_purchase(self, *, actor_id: int, purchase_id: int):
        purchase = self.repository.cancel_purchase(actor_id=actor_id, purchase_id=purchase_id)
        if purchase is None:
            raise PurchaseNotFound()
        return purchase

    def receive_purchase(self, *, actor_id: int, purchase_id: int, idempotency_key: UUID,
                         items: list[Mapping[str, object]], notes: str | None):
        if purchase_id < 1 or not items:
            raise PurchaseError("Indica una compra y al menos una cantidad recibida.", field="items")
        normalized: list[dict[str, object]] = []
        seen: set[int] = set()
        try:
            for index, item in enumerate(items):
                item_id, quantity = item.get("purchase_item_id"), item.get("quantity_received")
                if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id < 1 or item_id in seen:
                    raise PurchaseValidationFailure("La línea de compra es inválida o está repetida.", field=f"items.{index}.purchase_item_id")
                received = Decimal(str(quantity))
                if not received.is_finite() or received <= 0 or received.as_tuple().exponent < -3:
                    raise PurchaseValidationFailure("La cantidad recibida debe ser positiva y admitir hasta tres decimales.", field=f"items.{index}.quantity_received")
                normalized.append({"purchase_item_id": item_id, "quantity_received": received})
                seen.add(item_id)
        except (PurchaseValidationFailure, InvalidOperation, ValueError, TypeError) as exc:
            if isinstance(exc, PurchaseValidationFailure):
                raise _as_error(exc) from exc
            raise PurchaseError("La cantidad recibida no es válida.", field="items") from exc
        canonical = {"items": [{"purchase_item_id": x["purchase_item_id"], "quantity_received": str(x["quantity_received"])} for x in normalized], "notes": notes}
        request_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        receipt, replay = self.repository.receive_purchase(actor_id=actor_id, purchase_id=purchase_id,
                                                           idempotency_key=idempotency_key,
                                                           request_hash=request_hash,
                                                           values={"items": normalized, "notes": notes})
        return receipt, replay

    def list_receipts(self, purchase_id: int):
        if purchase_id < 1:
            raise PurchaseError("El identificador de compra no es válido.", field="purchase_id")
        receipts = self.repository.list_receipts(purchase_id)
        if receipts is None:
            raise PurchaseNotFound()
        return receipts
