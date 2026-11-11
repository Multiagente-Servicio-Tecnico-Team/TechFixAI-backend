"""Application service for supplier purchase orders."""
from collections.abc import Mapping
from datetime import date

from app.application.errors import PurchaseOrderError, PurchaseOrderNotFound
from app.domain.purchase_orders import (
    PurchaseOrderConflictFailure,
    PurchaseOrderValidationFailure,
    transition_order_status,
    validate_order_receipt,
    validate_purchase_order,
)
from uuid import UUID


class PurchaseOrderService:
    def __init__(self, repository):
        self.repository = repository

    def create_order(self, *, actor_id: int, values: Mapping[str, object]):
        if isinstance(actor_id, bool) or not isinstance(actor_id, int) or actor_id < 1:
            raise PurchaseOrderError("La sesión ADMIN no es válida.")
        try:
            draft = validate_purchase_order(values)
        except PurchaseOrderValidationFailure as exc:
            raise PurchaseOrderError(exc.detail, field=exc.field) from exc
        return self.repository.create_order(actor_id=actor_id, draft=draft)

    def get_order(self, order_id: int):
        if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1:
            raise PurchaseOrderError("El identificador de la orden no es válido.", field="order_id")
        order = self.repository.get_order(order_id)
        if order is None:
            raise PurchaseOrderNotFound()
        return order

    def update_draft_order(self, *, actor_id: int, order_id: int, values: Mapping[str, object]):
        allowed = {"supplier_id", "estimated_arrival", "notes", "items"}
        if isinstance(actor_id, bool) or not isinstance(actor_id, int) or actor_id < 1:
            raise PurchaseOrderError("La sesión ADMIN no es válida.")
        if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1:
            raise PurchaseOrderError("El identificador de la orden no es válido.", field="order_id")
        if not values or set(values) - allowed:
            raise PurchaseOrderError("Los campos de actualización no son válidos.")
        current = self.get_order(order_id)
        arrival = current.get("estimated_arrival")
        if isinstance(arrival, str):
            arrival = date.fromisoformat(arrival[:10])
        base = {
            "supplier_id": current["supplier_id"],
            "estimated_arrival": arrival,
            "notes": current.get("notes"),
            "items": [{
                "spare_part_id": item.get("spare_part_id"),
                "description": item.get("description_snapshot") or "",
                "quantity": int(item["quantity_ordered"]),
                "unit_cost": item["unit_cost"],
            } for item in current.get("items", [])],
        }
        base.update(values)
        try:
            draft = validate_purchase_order(base)
        except PurchaseOrderValidationFailure as exc:
            raise PurchaseOrderError(exc.detail, field=exc.field) from exc
        return self.repository.update_order(
            actor_id=actor_id,
            order_id=order_id,
            draft=draft,
            changed_fields=sorted(values),
        )

    def issue_order(self, *, actor_id: int, order_id: int):
        self._validate_actor_and_order(actor_id, order_id)
        current = self.get_order(order_id)
        try:
            transition_order_status(current["status"], "ISSUE")
        except PurchaseOrderConflictFailure as exc:
            from app.application.errors import PurchaseOrderConflict
            raise PurchaseOrderConflict(str(exc)) from exc
        return self.repository.issue_order(actor_id=actor_id, order_id=order_id)

    def cancel_order(self, *, actor_id: int, order_id: int, reason: str):
        self._validate_actor_and_order(actor_id, order_id)
        try:
            transition_order_status(self.get_order(order_id)["status"], "CANCEL", reason=reason)
        except PurchaseOrderValidationFailure as exc:
            raise PurchaseOrderError(exc.detail, field=exc.field) from exc
        except PurchaseOrderConflictFailure as exc:
            from app.application.errors import PurchaseOrderConflict
            raise PurchaseOrderConflict(str(exc)) from exc
        return self.repository.cancel_order(actor_id=actor_id, order_id=order_id, reason=reason.strip())

    def receive_order(self, *, actor_id: int, order_id: int, idempotency_key: UUID, values: Mapping[str, object]):
        self._validate_actor_and_order(actor_id, order_id)
        if not isinstance(idempotency_key, UUID):
            raise PurchaseOrderError("La clave de idempotencia no es válida.", field="Idempotency-Key")
        try:
            receipt = validate_order_receipt(values)
        except PurchaseOrderValidationFailure as exc:
            raise PurchaseOrderError(exc.detail, field=exc.field) from exc
        return self.repository.receive_order(
            actor_id=actor_id, order_id=order_id, idempotency_key=idempotency_key, receipt=receipt
        )

    def list_receipts(self, order_id: int):
        if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1:
            raise PurchaseOrderError("El identificador de la orden no es válido.", field="order_id")
        receipts = self.repository.list_receipts(order_id)
        if receipts is None:
            raise PurchaseOrderNotFound()
        return receipts

    def list_orders(self, *, supplier_id=None, status=None, date_from=None, date_to=None, limit=50, offset=0):
        if supplier_id is not None and (isinstance(supplier_id, bool) or not isinstance(supplier_id, int) or supplier_id < 1):
            raise PurchaseOrderError("El proveedor no es válido.", field="supplier_id")
        if status is not None and status not in {"DRAFT", "ISSUED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"}:
            raise PurchaseOrderError("El estado de la orden no es válido.", field="status")
        if date_from is not None and not isinstance(date_from, date):
            raise PurchaseOrderError("La fecha inicial no es válida.", field="date_from")
        if date_to is not None and not isinstance(date_to, date):
            raise PurchaseOrderError("La fecha final no es válida.", field="date_to")
        if date_from and date_to and date_to < date_from:
            raise PurchaseOrderError("La fecha final debe ser igual o posterior a la inicial.", field="date_to")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise PurchaseOrderError("El límite debe estar entre 1 y 100.", field="limit")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise PurchaseOrderError("El desplazamiento no es válido.", field="offset")
        return self.repository.list_orders(supplier_id=supplier_id, status=status, date_from=date_from,
                                           date_to=date_to, limit=limit, offset=offset)

    @staticmethod
    def _validate_actor_and_order(actor_id: int, order_id: int):
        if isinstance(actor_id, bool) or not isinstance(actor_id, int) or actor_id < 1:
            raise PurchaseOrderError("La sesión ADMIN no es válida.")
        if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1:
            raise PurchaseOrderError("El identificador de la orden no es válido.", field="order_id")
