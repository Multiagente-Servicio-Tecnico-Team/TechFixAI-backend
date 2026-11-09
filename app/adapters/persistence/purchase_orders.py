"""PostgreSQL adapter for purchase orders and physical order receipts."""
import json
import logging
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.errors import (
    PurchaseOrderConflict,
    PurchaseOrderNotFound,
    PurchaseOrderStorageUnavailable,
)
from app.domain.purchase_orders import (
    PurchaseOrderConflictFailure,
    transition_order_status,
    validate_order_receipt_quantities,
    next_order_receipt_status,
)
from app.adapters.persistence.inventory_movements import apply_stock_movement

logger = logging.getLogger(__name__)


def _default_session_factory():
    from app.database.connection import SessionLocal, get_engine
    get_engine()
    return SessionLocal


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value):
    return format(Decimal(str(value or 0)), ".2f")


def _quantity(value):
    return str(Decimal(str(value or 0)))


class PurchaseOrderRepositoryAdapter:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _default_session_factory()

    @staticmethod
    def _storage_error(exc):
        logger.error("Purchase order persistence failed: %s", type(exc).__name__)
        return PurchaseOrderStorageUnavailable()

    def create_order(self, *, actor_id, draft):
        try:
            with self._session_factory() as session, session.begin():
                supplier = session.execute(text(
                    "SELECT id FROM suppliers WHERE id=:id AND active=TRUE FOR SHARE"
                ), {"id": draft.supplier_id}).mappings().first()
                if supplier is None:
                    raise PurchaseOrderNotFound("El proveedor activo indicado no existe.", field="supplier_id")

                catalog_items = {}
                for line in draft.items:
                    if line.spare_part_id is None or line.spare_part_id in catalog_items:
                        continue
                    row = session.execute(text(
                        "SELECT id,code,name,active FROM spare_parts WHERE id=:id FOR SHARE"
                    ), {"id": line.spare_part_id}).mappings().first()
                    if row is None or not bool(row["active"]):
                        raise PurchaseOrderNotFound(
                            "Uno de los repuestos no existe o está inactivo.", field="spare_part_id"
                        )
                    catalog_items[line.spare_part_id] = row

                order_id = session.execute(text("""INSERT INTO purchase_orders
                    (supplier_id,total_amount,status,estimated_arrival,currency,notes,created_by_user_id)
                    VALUES (:supplier,:total,'DRAFT',:arrival,'PEN',:notes,:actor)
                    RETURNING id"""), {
                    "supplier": draft.supplier_id,
                    "total": draft.total_amount,
                    "arrival": draft.estimated_arrival,
                    "notes": draft.notes,
                    "actor": actor_id,
                }).scalar_one()

                for line in draft.items:
                    part = catalog_items.get(line.spare_part_id) if line.spare_part_id is not None else None
                    code_snapshot = part["code"] if part is not None else None
                    session.execute(text("""INSERT INTO purchase_order_items
                        (purchase_order_id,spare_part_id,custom_item_name,quantity,unit_cost,subtotal,
                         code_snapshot,description_snapshot)
                        VALUES (:order,:part,:custom,:quantity,:cost,:subtotal,:code,:description)"""), {
                        "order": order_id,
                        "part": line.spare_part_id,
                        "custom": line.description if line.spare_part_id is None else None,
                        "quantity": line.quantity,
                        "cost": line.unit_cost,
                        "subtotal": line.subtotal,
                        "code": code_snapshot,
                        "description": line.description,
                    })

                session.execute(text("""INSERT INTO purchase_order_audit_events
                    (purchase_order_id,actor_user_id,event_type,changed_fields)
                    VALUES (:order,:actor,'CREATED',CAST(:fields AS JSONB))"""), {
                    "order": order_id,
                    "actor": actor_id,
                    "fields": json.dumps({"status": "DRAFT", "total_amount": _money(draft.total_amount)}),
                })
            return self.get_order(int(order_id))
        except (PurchaseOrderNotFound, PurchaseOrderConflict):
            raise
        except IntegrityError as exc:
            raise PurchaseOrderConflict("La orden no pudo guardarse por una relación o dato en conflicto.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_order(self, *, actor_id, order_id, draft, changed_fields):
        try:
            with self._session_factory() as session, session.begin():
                order = session.execute(text("""SELECT status FROM purchase_orders
                    WHERE id=:id FOR UPDATE"""), {"id": order_id}).mappings().first()
                if order is None:
                    raise PurchaseOrderNotFound()
                if order["status"] != "DRAFT":
                    raise PurchaseOrderConflict("Solo se pueden editar órdenes en borrador.")
                has_receipts = session.execute(text("""SELECT EXISTS(
                    SELECT 1 FROM purchase_order_receipts WHERE purchase_order_id=:id)"""), {
                    "id": order_id,
                }).scalar_one()
                has_purchases = session.execute(text("""SELECT EXISTS(
                    SELECT 1 FROM supplier_purchases WHERE purchase_order_id=:id)"""), {
                    "id": order_id,
                }).scalar_one()
                if has_receipts or has_purchases:
                    raise PurchaseOrderConflict("No se puede editar una orden con recepciones o facturas vinculadas.")

                supplier = session.execute(text(
                    "SELECT id FROM suppliers WHERE id=:id AND active=TRUE FOR SHARE"
                ), {"id": draft.supplier_id}).mappings().first()
                if supplier is None:
                    raise PurchaseOrderNotFound("El proveedor activo indicado no existe.", field="supplier_id")

                catalog_items = {}
                for line in draft.items:
                    if line.spare_part_id is None or line.spare_part_id in catalog_items:
                        continue
                    part = session.execute(text(
                        "SELECT id,code,name,active FROM spare_parts WHERE id=:id FOR SHARE"
                    ), {"id": line.spare_part_id}).mappings().first()
                    if part is None or not bool(part["active"]):
                        raise PurchaseOrderNotFound(
                            "Uno de los repuestos no existe o está inactivo.", field="spare_part_id"
                        )
                    catalog_items[line.spare_part_id] = part

                session.execute(text("""UPDATE purchase_orders SET supplier_id=:supplier,
                    total_amount=:total,estimated_arrival=:arrival,notes=:notes,updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id"""), {
                    "supplier": draft.supplier_id, "total": draft.total_amount,
                    "arrival": draft.estimated_arrival, "notes": draft.notes, "id": order_id,
                })
                session.execute(text("DELETE FROM purchase_order_items WHERE purchase_order_id=:id"), {"id": order_id})
                for line in draft.items:
                    part = catalog_items.get(line.spare_part_id) if line.spare_part_id is not None else None
                    session.execute(text("""INSERT INTO purchase_order_items
                        (purchase_order_id,spare_part_id,custom_item_name,quantity,unit_cost,subtotal,
                         code_snapshot,description_snapshot)
                        VALUES (:order,:part,:custom,:quantity,:cost,:subtotal,:code,:description)"""), {
                        "order": order_id,
                        "part": line.spare_part_id,
                        "custom": line.description if line.spare_part_id is None else None,
                        "quantity": line.quantity,
                        "cost": line.unit_cost,
                        "subtotal": line.subtotal,
                        "code": part["code"] if part is not None else None,
                        "description": line.description,
                    })
                session.execute(text("""INSERT INTO purchase_order_audit_events
                    (purchase_order_id,actor_user_id,event_type,changed_fields)
                    VALUES (:order,:actor,'UPDATED',CAST(:fields AS JSONB))"""), {
                    "order": order_id, "actor": actor_id,
                    "fields": json.dumps({"changed_fields": changed_fields,
                                          "total_amount": _money(draft.total_amount)}),
                })
            return self.get_order(order_id)
        except (PurchaseOrderNotFound, PurchaseOrderConflict):
            raise
        except IntegrityError as exc:
            raise PurchaseOrderConflict("La orden no pudo actualizarse por una relación o dato en conflicto.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def issue_order(self, *, actor_id, order_id):
        try:
            with self._session_factory() as session, session.begin():
                order = session.execute(text(
                    "SELECT status FROM purchase_orders WHERE id=:id FOR UPDATE"
                ), {"id": order_id}).mappings().first()
                if order is None:
                    raise PurchaseOrderNotFound()
                try:
                    transition_order_status(order["status"], "ISSUE")
                except PurchaseOrderConflictFailure as exc:
                    raise PurchaseOrderConflict(str(exc)) from exc
                session.execute(text("""UPDATE purchase_orders
                    SET status='ISSUED',issued_by_user_id=:actor,issued_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP WHERE id=:id"""), {
                    "actor": actor_id, "id": order_id,
                })
                session.execute(text("""INSERT INTO purchase_order_audit_events
                    (purchase_order_id,actor_user_id,event_type,changed_fields)
                    VALUES (:order,:actor,'ISSUED',CAST(:fields AS JSONB))"""), {
                    "order": order_id, "actor": actor_id,
                    "fields": json.dumps({"status": {"from": order["status"], "to": "ISSUED"}}),
                })
            return self.get_order(order_id)
        except (PurchaseOrderNotFound, PurchaseOrderConflict):
            raise
        except IntegrityError as exc:
            raise PurchaseOrderConflict("La orden no pudo emitirse por un dato en conflicto.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def cancel_order(self, *, actor_id, order_id, reason):
        try:
            with self._session_factory() as session, session.begin():
                order = session.execute(text(
                    "SELECT status FROM purchase_orders WHERE id=:id FOR UPDATE"
                ), {"id": order_id}).mappings().first()
                if order is None:
                    raise PurchaseOrderNotFound()
                received = session.execute(text("""SELECT COALESCE(SUM(ri.quantity_received),0)
                    FROM purchase_order_receipt_items ri
                    JOIN purchase_order_receipts r ON r.id=ri.receipt_id
                    WHERE r.purchase_order_id=:id"""), {"id": order_id}).scalar_one()
                ordered = session.execute(text("""SELECT COALESCE(SUM(quantity),0)
                    FROM purchase_order_items WHERE purchase_order_id=:id"""), {"id": order_id}).scalar_one()
                if order["status"] == "RECEIVED" or (ordered and received >= ordered):
                    raise PurchaseOrderConflict("No se puede cancelar una orden completamente recibida.")
                try:
                    transition_order_status(order["status"], "CANCEL", reason=reason)
                except PurchaseOrderConflictFailure as exc:
                    raise PurchaseOrderConflict(str(exc)) from exc
                session.execute(text("""UPDATE purchase_orders SET status='CANCELLED',
                    cancelled_by_user_id=:actor,cancelled_at=CURRENT_TIMESTAMP,
                    cancellation_reason=:reason,updated_at=CURRENT_TIMESTAMP WHERE id=:id"""), {
                    "actor": actor_id, "reason": reason.strip(), "id": order_id,
                })
                session.execute(text("""INSERT INTO purchase_order_audit_events
                    (purchase_order_id,actor_user_id,event_type,changed_fields)
                    VALUES (:order,:actor,'CANCELLED',CAST(:fields AS JSONB))"""), {
                    "order": order_id, "actor": actor_id,
                    "fields": json.dumps({"status": {"from": order["status"], "to": "CANCELLED"},
                                          "reason": reason.strip(),
                                          "quantity_received": _quantity(received)}),
                })
            return self.get_order(order_id)
        except (PurchaseOrderNotFound, PurchaseOrderConflict):
            raise
        except IntegrityError as exc:
            raise PurchaseOrderConflict("La orden no pudo cancelarse por un dato en conflicto.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def receive_order(self, *, actor_id, order_id, idempotency_key, receipt):
        try:
            replay = False
            with self._session_factory() as session, session.begin():
                order = session.execute(text(
                    "SELECT status FROM purchase_orders WHERE id=:id FOR UPDATE"
                ), {"id": order_id}).mappings().first()
                if order is None:
                    raise PurchaseOrderNotFound()
                prior = session.execute(text("""SELECT id,request_hash FROM purchase_order_receipts
                    WHERE purchase_order_id=:order AND actor_user_id=:actor AND idempotency_key=:key"""), {
                    "order": order_id, "actor": actor_id, "key": idempotency_key,
                }).mappings().first()
                if prior:
                    if prior["request_hash"] != receipt.request_hash:
                        raise PurchaseOrderConflict("La clave de idempotencia ya se usó con otros datos.")
                    receipt_id, replay = int(prior["id"]), True
                else:
                    if order["status"] not in {"ISSUED", "PARTIALLY_RECEIVED"}:
                        raise PurchaseOrderConflict("Solo se reciben órdenes emitidas y no canceladas.")
                    lines = session.execute(text("""SELECT i.id,i.quantity,i.spare_part_id,
                        i.code_snapshot,i.description_snapshot,
                        COALESCE((SELECT SUM(ri.quantity_received) FROM purchase_order_receipt_items ri
                            JOIN purchase_order_receipts r ON r.id=ri.receipt_id
                            WHERE r.purchase_order_id=:order AND ri.purchase_order_item_id=i.id),0) AS received
                        FROM purchase_order_items i WHERE i.purchase_order_id=:order
                        ORDER BY i.id FOR UPDATE OF i"""), {"order": order_id}).mappings().all()
                    by_id = {int(line["id"]): line for line in lines}
                    incoming = dict(receipt.items)
                    ordered = {int(line["id"]): int(line["quantity"]) for line in lines}
                    already = {int(line["id"]): int(line["received"]) for line in lines}
                    try:
                        totals = validate_order_receipt_quantities(ordered, already, incoming)
                        new_status = next_order_receipt_status(order["status"], ordered, totals)
                    except PurchaseOrderConflictFailure as exc:
                        raise PurchaseOrderConflict(str(exc)) from exc

                    receipt_id = session.execute(text("""INSERT INTO purchase_order_receipts
                        (purchase_order_id,actor_user_id,idempotency_key,request_hash,notes)
                        VALUES (:order,:actor,:key,:hash,:notes) RETURNING id"""), {
                        "order": order_id, "actor": actor_id, "key": idempotency_key,
                        "hash": receipt.request_hash, "notes": receipt.notes,
                    }).scalar_one()
                    for line_id, quantity in receipt.items:
                        line = by_id[line_id]
                        receipt_line_id = session.execute(text("""INSERT INTO purchase_order_receipt_items
                            (receipt_id,purchase_order_item_id,quantity_received)
                            VALUES (:receipt,:line,:quantity) RETURNING id"""), {
                            "receipt": receipt_id, "line": line_id, "quantity": quantity,
                        }).scalar_one()
                        if line["spare_part_id"] is not None:
                            try:
                                apply_stock_movement(
                                    session, part_id=int(line["spare_part_id"]), quantity_delta=quantity,
                                    movement_type="PURCHASE_RECEIPT", actor_user_id=actor_id,
                                    purchase_order_receipt_item_id=int(receipt_line_id),
                                    code_snapshot=line["code_snapshot"],
                                    name_snapshot=line["description_snapshot"],
                                )
                            except ValueError as exc:
                                raise PurchaseOrderConflict(str(exc)) from exc
                    session.execute(text("""UPDATE purchase_orders SET status=:status,
                        updated_at=CURRENT_TIMESTAMP WHERE id=:order"""), {
                        "status": new_status, "order": order_id,
                    })
                    session.execute(text("""INSERT INTO purchase_order_audit_events
                        (purchase_order_id,actor_user_id,event_type,changed_fields)
                        VALUES (:order,:actor,'RECEIPT_CONFIRMED',CAST(:fields AS JSONB))"""), {
                        "order": order_id, "actor": actor_id,
                        "fields": json.dumps({"receipt_id": int(receipt_id), "status": new_status,
                                              "items": [{"purchase_order_item_id": line_id,
                                                         "quantity_received": quantity}
                                                        for line_id, quantity in receipt.items]}),
                    })
            return self._receipt_detail(int(receipt_id)), replay
        except (PurchaseOrderNotFound, PurchaseOrderConflict):
            raise
        except IntegrityError as exc:
            raise PurchaseOrderConflict("La recepción entra en conflicto con el estado de la orden.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def _receipt_detail(self, receipt_id):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT id,purchase_order_id,actor_user_id,received_at,notes
                FROM purchase_order_receipts WHERE id=:id"""), {"id": receipt_id}).mappings().first()
            if row is None:
                return None
            items = session.execute(text("""SELECT ri.purchase_order_item_id,ri.quantity_received,
                im.id AS movement_id,im.stock_before,im.stock_after,im.quantity_delta
                FROM purchase_order_receipt_items ri
                LEFT JOIN inventory_movements im ON im.purchase_order_receipt_item_id=ri.id
                WHERE ri.receipt_id=:id ORDER BY ri.id"""), {"id": receipt_id}).mappings().all()
            return {
                "id": int(row["id"]), "purchase_order_id": int(row["purchase_order_id"]),
                "received_by": int(row["actor_user_id"]), "received_at": _iso(row["received_at"]),
                "notes": row["notes"], "items": [{
                    "purchase_order_item_id": int(item["purchase_order_item_id"]),
                    "quantity_received": _quantity(item["quantity_received"]),
                    "movement": None if item["movement_id"] is None else {
                        "id": int(item["movement_id"]), "quantity_delta": int(item["quantity_delta"]),
                        "stock_before": int(item["stock_before"]), "stock_after": int(item["stock_after"]),
                    },
                } for item in items],
            }

    def list_receipts(self, order_id):
        try:
            with self._session_factory() as session:
                exists = session.execute(text(
                    "SELECT 1 FROM purchase_orders WHERE id=:id"
                ), {"id": order_id}).first()
                if exists is None:
                    return None
                ids = session.execute(text("""SELECT id FROM purchase_order_receipts
                    WHERE purchase_order_id=:id ORDER BY received_at,id"""), {"id": order_id}).scalars().all()
            return [self._receipt_detail(int(receipt_id)) for receipt_id in ids]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def get_order(self, order_id):
        try:
            with self._session_factory() as session:
                row = session.execute(text("""SELECT po.id,po.supplier_id,s.name AS supplier_name,
                    po.status,po.total_amount,po.currency,po.estimated_arrival,
                    po.created_by_user_id,po.issued_by_user_id,po.issued_at,
                    po.cancelled_by_user_id,po.cancelled_at,po.cancellation_reason,
                    po.created_at,po.updated_at,po.notes
                    FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id
                    WHERE po.id=:id"""), {"id": order_id}).mappings().first()
                if row is None:
                    return None
                raw_lines = session.execute(text("""SELECT i.id,i.spare_part_id,i.code_snapshot,
                    i.description_snapshot,i.quantity,i.unit_cost,i.subtotal,
                    COALESCE((SELECT SUM(ri.quantity_received)
                        FROM purchase_order_receipt_items ri
                        JOIN purchase_order_receipts r ON r.id=ri.receipt_id
                        WHERE ri.purchase_order_item_id=i.id),0) AS quantity_received,
                    CASE
                      WHEN EXISTS (SELECT 1 FROM supplier_purchases p
                          JOIN supplier_purchase_items pi ON pi.purchase_id=p.id
                          WHERE p.purchase_order_id=:order AND pi.purchase_order_item_id IS NULL)
                      THEN NULL
                      ELSE COALESCE((SELECT SUM(pi.quantity)
                          FROM supplier_purchase_items pi
                          JOIN supplier_purchases p ON p.id=pi.purchase_id
                          WHERE p.purchase_order_id=:order AND pi.purchase_order_item_id=i.id),0)
                    END AS quantity_invoiced
                    FROM purchase_order_items i WHERE i.purchase_order_id=:order ORDER BY i.id"""), {
                    "order": order_id,
                }).mappings().all()
                receipts = session.execute(text("""SELECT r.id,r.purchase_order_id,r.actor_user_id,
                    r.received_at,r.notes FROM purchase_order_receipts r
                    WHERE r.purchase_order_id=:order ORDER BY r.received_at,r.id"""), {
                    "order": order_id,
                }).mappings().all()
                receipt_ids = [int(receipt["id"]) for receipt in receipts]
                receipt_items = {}
                for receipt_id in receipt_ids:
                    items = session.execute(text("""SELECT ri.purchase_order_item_id,ri.quantity_received,
                        im.id AS movement_id,im.quantity_delta,im.stock_before,im.stock_after
                        FROM purchase_order_receipt_items ri
                        LEFT JOIN inventory_movements im ON im.purchase_order_receipt_item_id=ri.id
                        WHERE ri.receipt_id=:id ORDER BY ri.id"""), {
                        "id": receipt_id,
                    }).mappings().all()
                    receipt_items[receipt_id] = [
                        {"purchase_order_item_id": int(item["purchase_order_item_id"]),
                         "quantity_received": _quantity(item["quantity_received"]),
                         "movement": None if item["movement_id"] is None else {
                             "id": int(item["movement_id"]), "quantity_delta": int(item["quantity_delta"]),
                             "stock_before": int(item["stock_before"]), "stock_after": int(item["stock_after"]),
                         }}
                        for item in items
                    ]
                linked = session.execute(text("""SELECT id,document_type,document_number,issue_date,
                    total_amount,status,payment_status FROM supplier_purchases
                    WHERE purchase_order_id=:order ORDER BY issue_date,id"""), {"order": order_id}).mappings().all()
                events = session.execute(text("""SELECT id,actor_user_id,event_type,changed_fields,created_at
                    FROM purchase_order_audit_events WHERE purchase_order_id=:order
                    ORDER BY created_at,id"""), {"order": order_id}).mappings().all()

            items = []
            received_by_line = {}
            for line in raw_lines:
                received = Decimal(str(line["quantity_received"] or 0))
                quantity = Decimal(str(line["quantity"]))
                received_by_line[int(line["id"])] = received
                items.append({
                    "id": int(line["id"]),
                    "spare_part_id": int(line["spare_part_id"]) if line["spare_part_id"] is not None else None,
                    "code_snapshot": line["code_snapshot"],
                    "description_snapshot": line["description_snapshot"],
                    "quantity_ordered": _quantity(quantity),
                    "quantity_received": _quantity(received),
                    "quantity_pending": _quantity(
                        Decimal("0") if row["status"] == "CANCELLED"
                        else max(Decimal("0"), quantity - received)
                    ),
                    "quantity_invoiced": _quantity(line["quantity_invoiced"]) if line["quantity_invoiced"] is not None else None,
                    "quantity_cancelled": _quantity(max(Decimal("0"), quantity - received)) if row["status"] == "CANCELLED" else "0",
                    "unit_cost": _money(line["unit_cost"]),
                    "subtotal": _money(line["subtotal"]),
                })
            return {
                "id": int(row["id"]),
                "supplier_id": int(row["supplier_id"]),
                "supplier_name": row["supplier_name"],
                "status": row["status"],
                "total_amount": _money(row["total_amount"]),
                "currency": str(row["currency"]).strip(),
                "estimated_arrival": _iso(row["estimated_arrival"]),
                "created_by": int(row["created_by_user_id"]),
                "issued_by": int(row["issued_by_user_id"]) if row["issued_by_user_id"] is not None else None,
                "issued_at": _iso(row["issued_at"]),
                "cancelled_by": int(row["cancelled_by_user_id"]) if row["cancelled_by_user_id"] is not None else None,
                "cancelled_at": _iso(row["cancelled_at"]),
                "cancellation_reason": row["cancellation_reason"],
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
                "notes": row["notes"],
                "items": items,
                "receipts": [{
                    "id": int(receipt["id"]),
                    "purchase_order_id": int(receipt["purchase_order_id"]),
                    "received_by": int(receipt["actor_user_id"]),
                    "received_at": _iso(receipt["received_at"]),
                    "notes": receipt["notes"],
                    "items": receipt_items[int(receipt["id"])],
                } for receipt in receipts],
                "linked_purchases": [{
                    "id": int(purchase["id"]), "document_type": purchase["document_type"],
                    "document_number": purchase["document_number"], "issue_date": _iso(purchase["issue_date"]),
                    "total_amount": _money(purchase["total_amount"]), "status": purchase["status"],
                    "payment_status": purchase["payment_status"],
                } for purchase in linked],
                "audit_events": [{
                    "id": int(event["id"]), "actor_user_id": int(event["actor_user_id"]),
                    "event_type": event["event_type"], "changed_fields": event["changed_fields"],
                    "created_at": _iso(event["created_at"]),
                } for event in events],
            }
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_orders(self, *, supplier_id=None, status=None, date_from=None, date_to=None, limit=50, offset=0):
        conditions = []
        params = {"limit": limit, "offset": offset}
        if supplier_id is not None:
            conditions.append("po.supplier_id=:supplier_id")
            params["supplier_id"] = supplier_id
        if status is not None:
            conditions.append("po.status=:status")
            params["status"] = status
        if date_from is not None:
            conditions.append("po.created_at >= CAST(:date_from AS DATE)")
            params["date_from"] = date_from
        if date_to is not None:
            conditions.append("po.created_at < (CAST(:date_to AS DATE) + INTERVAL '1 day')")
            params["date_to"] = date_to
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        try:
            with self._session_factory() as session:
                total = int(session.execute(text("SELECT count(*) FROM purchase_orders po" + where), params).scalar_one())
                rows = session.execute(text("""SELECT po.id,po.supplier_id,s.name AS supplier_name,po.status,
                    po.total_amount,po.currency,po.estimated_arrival,po.created_at
                    FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id""" + where +
                    " ORDER BY po.created_at DESC,po.id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
            return {
                "items": [{
                    "id": int(row["id"]), "supplier_id": int(row["supplier_id"]),
                    "supplier_name": row["supplier_name"], "status": row["status"],
                    "total_amount": _money(row["total_amount"]), "currency": str(row["currency"]).strip(),
                    "estimated_arrival": _iso(row["estimated_arrival"]), "created_at": _iso(row["created_at"]),
                } for row in rows],
                "total": total, "limit": limit, "offset": offset,
            }
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc
