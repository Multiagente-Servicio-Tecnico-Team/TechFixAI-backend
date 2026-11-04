"""Adaptador PostgreSQL para proveedores, compras y recepciones."""
import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.errors import (
    PurchaseConflict, PurchaseError, PurchaseNotFound, PurchaseStorageUnavailable,
    SupplierNotFound,
)
from app.domain.purchases import PurchaseConflictFailure, next_receipt_status

logger = logging.getLogger(__name__)


def _default_session_factory():
    from app.database.connection import SessionLocal, get_engine
    get_engine()
    return SessionLocal


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value):
    return format(Decimal(str(value or 0)), ".2f")


class SupplierPurchaseRepositoryAdapter:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _default_session_factory()

    @staticmethod
    def _storage_error(exc):
        logger.error("Supplier purchase persistence failed: %s", type(exc).__name__)
        return PurchaseStorageUnavailable()

    @staticmethod
    def _supplier(row):
        if row is None:
            return None
        return {"id": int(row["id"]), "name": row["name"], "tax_id": row["tax_id"],
                "contact_name": row["contact_name"], "contact_email": row["contact_email"],
                "phone": row["phone"], "address": row["address"],
                "delivery_lead_days": row["delivery_lead_days"], "active": bool(row["active"]),
                "created_at": _iso(row["created_at"])}

    @staticmethod
    def _line(row):
        return {"id": int(row["id"]), "spare_part_id": int(row["spare_part_id"]) if row["spare_part_id"] is not None else None,
                "code_snapshot": row["code_snapshot"], "description": row["description_snapshot"],
                "quantity": str(row["quantity"]), "unit_cost": _money(row["unit_cost"]),
                "discount_amount": _money(row["discount_amount"]), "tax_amount": _money(row["tax_amount"]),
                "line_total": _money(row["line_total"])}

    def list_suppliers(self, *, active=None, search=None, limit=50, offset=0):
        clauses, params = [], {"limit": limit, "offset": offset}
        if active is not None:
            clauses.append("active = :active")
            params["active"] = active
        if search:
            clauses.append("(name ILIKE :search OR tax_id ILIKE :search OR contact_name ILIKE :search)")
            params["search"] = f"%{search.strip()}%"
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        try:
            with self._session_factory() as session:
                total = int(session.execute(text("SELECT count(*) FROM suppliers" + where), params).scalar_one())
                rows = session.execute(text("SELECT id,name,tax_id,contact_name,contact_email,phone,address,delivery_lead_days,active,created_at FROM suppliers" + where + " ORDER BY name,id LIMIT :limit OFFSET :offset"), params).mappings().all()
            return {"items": [self._supplier(row) for row in rows], "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def get_supplier(self, supplier_id):
        try:
            with self._session_factory() as session:
                row = session.execute(text("SELECT id,name,tax_id,contact_name,contact_email,phone,address,delivery_lead_days,active,created_at FROM suppliers WHERE id=:id"), {"id": supplier_id}).mappings().first()
            return self._supplier(row)
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def create_supplier(self, values):
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(text("""INSERT INTO suppliers
                    (name,tax_id,contact_name,contact_email,phone,address,delivery_lead_days,active)
                    VALUES (:name,:tax_id,:contact_name,:contact_email,:phone,:address,:delivery_lead_days,TRUE)
                    RETURNING id,name,tax_id,contact_name,contact_email,phone,address,delivery_lead_days,active,created_at"""), values).mappings().one()
            return self._supplier(row)
        except IntegrityError as exc:
            raise PurchaseConflict("El identificador tributario ya está asociado a otro proveedor.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_supplier(self, supplier_id, values):
        allowed = {"name", "tax_id", "contact_name", "contact_email", "phone", "address", "delivery_lead_days", "active"}
        if not values or set(values) - allowed:
            raise PurchaseError("Los campos de proveedor no son válidos.")
        assignments = ",".join(f"{key} = :{key}" for key in values)
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(text(f"""UPDATE suppliers SET {assignments}
                    WHERE id=:id RETURNING id,name,tax_id,contact_name,contact_email,phone,address,delivery_lead_days,active,created_at"""), {**values, "id": supplier_id}).mappings().first()
            return self._supplier(row)
        except IntegrityError as exc:
            raise PurchaseConflict("El identificador tributario ya está asociado a otro proveedor.") from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def create_purchase(self, *, actor_id: int, draft, values):
        try:
            with self._session_factory() as session, session.begin():
                supplier = session.execute(text("SELECT id,name,tax_id,active FROM suppliers WHERE id=:id FOR SHARE"), {"id": draft.supplier_id}).mappings().first()
                if supplier is None or not supplier["active"]:
                    raise SupplierNotFound("Selecciona un proveedor activo.")
                if draft.purchase_order_id is not None:
                    order = session.execute(text("SELECT id,supplier_id FROM purchase_orders WHERE id=:id FOR SHARE"), {"id": draft.purchase_order_id}).mappings().first()
                    if order is None or int(order["supplier_id"]) != draft.supplier_id:
                        raise PurchaseError("La orden no existe o pertenece a otro proveedor.", field="purchase_order_id")
                snapshots = []
                for line in draft.lines:
                    part = None
                    if line.spare_part_id is not None:
                        part = session.execute(text("SELECT id,code,name FROM spare_parts WHERE id=:id FOR SHARE"), {"id": line.spare_part_id}).mappings().first()
                        if part is None:
                            raise PurchaseError("El repuesto asociado ya no existe.", field="spare_part_id")
                    snapshots.append((line, part))
                purchase_id = session.execute(text("""INSERT INTO supplier_purchases
                    (supplier_id,purchase_order_id,supplier_name_snapshot,supplier_tax_id_snapshot,
                     document_type,document_series,document_number,issue_date,due_date,currency,subtotal,
                     tax_total,discount_total,other_charges,total_amount,payment_method,payment_status,
                     status,notes,created_by)
                    VALUES (:supplier_id,:order_id,:supplier_name,:tax_id,:document_type,:series,:number,
                     :issue_date,:due_date,'PEN',:subtotal,:tax,:discount,:charges,:total,:method,:payment_status,
                     'REGISTERED',:notes,:actor) RETURNING id"""), {
                    "supplier_id": draft.supplier_id, "order_id": draft.purchase_order_id,
                    "supplier_name": supplier["name"], "tax_id": supplier["tax_id"],
                    "document_type": draft.document_type, "series": draft.document_series,
                    "number": draft.document_number, "issue_date": draft.issue_date, "due_date": draft.due_date,
                    "subtotal": draft.subtotal, "tax": draft.tax_total, "discount": draft.discount_total,
                    "charges": draft.other_charges, "total": draft.total_amount,
                    "method": draft.payment_method, "payment_status": draft.payment_status,
                    "notes": draft.notes, "actor": actor_id,
                }).scalar_one()
                for line, part in snapshots:
                    session.execute(text("""INSERT INTO supplier_purchase_items
                        (purchase_id,spare_part_id,code_snapshot,description_snapshot,quantity,unit_cost,
                         discount_amount,tax_amount,line_total)
                        VALUES (:purchase_id,:part_id,:code,:description,:quantity,:cost,:discount,:tax,:total)"""), {
                        "purchase_id": purchase_id, "part_id": part["id"] if part else None,
                        "code": part["code"] if part else None,
                        "description": line.description, "quantity": line.quantity,
                        "cost": line.unit_cost, "discount": line.discount_amount,
                        "tax": line.tax_amount, "total": line.line_total,
                    })
                session.execute(text("INSERT INTO supplier_purchase_audit_events (purchase_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'CREATED',CAST(:fields AS JSONB))"),
                                {"id": purchase_id, "actor": actor_id, "fields": json.dumps({"status": "REGISTERED"})})
            return self.get_purchase(int(purchase_id))
        except (PurchaseError, SupplierNotFound):
            raise
        except IntegrityError as exc:
            message = str(getattr(exc, "orig", exc)).lower()
            if "ux_supplier_purchase_document" in message:
                raise PurchaseConflict("Ya existe un comprobante con ese proveedor, tipo, serie y número.") from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def _detail(self, session, purchase_id):
        header = session.execute(text("""SELECT p.*,trim(u.name || ' ' || coalesce(u.last_name,'')) AS responsible_name
            FROM supplier_purchases p JOIN users u ON u.id=p.created_by WHERE p.id=:id"""), {"id": purchase_id}).mappings().first()
        if header is None:
            return None
        line_rows = session.execute(text("SELECT * FROM supplier_purchase_items WHERE purchase_id=:id ORDER BY id"), {"id": purchase_id}).mappings().all()
        receipt_rows = session.execute(text("""SELECT r.id,r.purchase_id,r.received_at,r.actor_user_id,
            trim(u.name || ' ' || coalesce(u.last_name,'')) AS actor_name,r.notes
            FROM purchase_receipts r JOIN users u ON u.id=r.actor_user_id WHERE r.purchase_id=:id ORDER BY r.received_at,r.id"""), {"id": purchase_id}).mappings().all()
        receipts = []
        for receipt in receipt_rows:
            items = session.execute(text("""SELECT ri.purchase_item_id,ri.quantity_received,im.id AS movement_id,
                im.spare_part_id,im.code_snapshot,im.name_snapshot,im.quantity_delta,im.stock_before,im.stock_after
                FROM purchase_receipt_items ri LEFT JOIN inventory_movements im ON im.purchase_receipt_item_id=ri.id
                WHERE ri.receipt_id=:id ORDER BY ri.id"""), {"id": receipt["id"]}).mappings().all()
            receipts.append({"id": int(receipt["id"]), "purchase_id": purchase_id,
                "received_at": _iso(receipt["received_at"]), "received_by": int(receipt["actor_user_id"]),
                "actor_name": receipt["actor_name"], "notes": receipt["notes"],
                "items": [{"purchase_item_id": int(x["purchase_item_id"]), "quantity_received": str(x["quantity_received"]),
                    "movement": None if x["movement_id"] is None else {"id": int(x["movement_id"]),
                        "spare_part_id": int(x["spare_part_id"]) if x["spare_part_id"] is not None else None,
                        "code_snapshot": x["code_snapshot"], "name_snapshot": x["name_snapshot"],
                        "quantity_delta": int(x["quantity_delta"]), "stock_before": int(x["stock_before"]),
                        "stock_after": int(x["stock_after"])}} for x in items]})
        events = session.execute(text("""SELECT e.event_type,e.changed_fields,e.created_at,e.actor_user_id,
            trim(u.name || ' ' || coalesce(u.last_name,'')) AS actor_name FROM supplier_purchase_audit_events e
            JOIN users u ON u.id=e.actor_user_id WHERE e.purchase_id=:id ORDER BY e.created_at,e.id"""), {"id": purchase_id}).mappings().all()
        return {"id": int(header["id"]), "supplier_id": int(header["supplier_id"]),
            "supplier_name": header["supplier_name_snapshot"], "supplier_tax_id": header["supplier_tax_id_snapshot"],
            "purchase_order_id": int(header["purchase_order_id"]) if header["purchase_order_id"] is not None else None,
            "document_type": header["document_type"], "document_series": header["document_series"],
            "document_number": header["document_number"], "issue_date": _iso(header["issue_date"]),
            "due_date": _iso(header["due_date"]), "currency": header["currency"],
            "subtotal": _money(header["subtotal"]), "tax_total": _money(header["tax_total"]),
            "discount_total": _money(header["discount_total"]), "other_charges": _money(header["other_charges"]),
            "total_amount": _money(header["total_amount"]), "payment_method": header["payment_method"],
            "payment_status": header["payment_status"], "status": header["status"], "notes": header["notes"],
            "created_by": int(header["created_by"]), "responsible_name": header["responsible_name"],
            "created_at": _iso(header["created_at"]), "updated_at": _iso(header["updated_at"]),
            "items": [self._line(row) for row in line_rows], "receipts": receipts,
            "audit_events": [{"event_type": x["event_type"], "changed_fields": x["changed_fields"],
                              "actor_user_id": int(x["actor_user_id"]), "actor_name": x["actor_name"],
                              "created_at": _iso(x["created_at"])} for x in events]}

    def get_purchase(self, purchase_id):
        try:
            with self._session_factory() as session:
                return self._detail(session, purchase_id)
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_purchases(self, *, supplier_id=None, from_date=None, to_date=None, status=None,
                       payment_status=None, document_number=None, limit=50, offset=0):
        conditions, params = [], {"limit": limit, "offset": offset}
        for key, value, clause in (("supplier_id", supplier_id, "p.supplier_id=:supplier_id"),
            ("from_date", from_date, "p.issue_date>=:from_date"), ("to_date", to_date, "p.issue_date<=:to_date"),
            ("status", status, "p.status=:status"), ("payment_status", payment_status, "p.payment_status=:payment_status")):
            if value is not None:
                conditions.append(clause); params[key] = value
        if document_number:
            conditions.append("p.document_number ILIKE :document_number")
            params["document_number"] = f"%{document_number.strip()}%"
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        try:
            with self._session_factory() as session:
                total = int(session.execute(text("SELECT count(*) FROM supplier_purchases p" + where), params).scalar_one())
                rows = session.execute(text("""SELECT p.id,p.supplier_id,p.supplier_name_snapshot,p.document_type,
                    p.document_number,p.issue_date,p.total_amount,p.status,p.payment_status
                    FROM supplier_purchases p""" + where + " ORDER BY p.issue_date DESC,p.id DESC LIMIT :limit OFFSET :offset"), params).mappings().all()
            return {"items": [{"id": int(r["id"]), "supplier_id": int(r["supplier_id"]),
                "supplier_name": r["supplier_name_snapshot"], "document_type": r["document_type"],
                "document_number": r["document_number"], "issue_date": _iso(r["issue_date"]),
                "total_amount": _money(r["total_amount"]), "status": r["status"],
                "payment_status": r["payment_status"]} for r in rows], "total": total, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_purchase(self, *, actor_id, purchase_id, values):
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(text("SELECT status,payment_status,notes FROM supplier_purchases WHERE id=:id FOR UPDATE"), {"id": purchase_id}).mappings().first()
                if row is None:
                    return None
                if row["status"] == "CANCELLED":
                    raise PurchaseConflict("No se puede modificar una compra cancelada.")
                changes = {}
                if "payment_status" in values:
                    new_status = values["payment_status"]
                    if row["payment_status"] == "PAID" and new_status != "PAID":
                        raise PurchaseConflict("El estado de pago no puede volver de pagado a pendiente.")
                    if new_status == "PAID" and row["payment_status"] == "PENDING":
                        changes["payment_status"] = new_status
                if "notes" in values and row["notes"] != values["notes"]:
                    changes["notes"] = values["notes"]
                if changes:
                    assignments = ",".join(f"{key}=:{key}" for key in changes)
                    session.execute(text(f"UPDATE supplier_purchases SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=:id"), {**changes,"id":purchase_id})
                    event_type = "PAYMENT_STATUS_CHANGED" if "payment_status" in changes else "UPDATED"
                    session.execute(text("INSERT INTO supplier_purchase_audit_events (purchase_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,:event,CAST(:fields AS JSONB))"), {"id":purchase_id,"actor":actor_id,"event":event_type,"fields":json.dumps(changes)})
            return self.get_purchase(purchase_id)
        except PurchaseConflict:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def cancel_purchase(self, *, actor_id, purchase_id):
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(text("SELECT status FROM supplier_purchases WHERE id=:id FOR UPDATE"), {"id":purchase_id}).mappings().first()
                if row is None:
                    return None
                if row["status"] != "REGISTERED":
                    raise PurchaseConflict("Sólo se puede cancelar una compra que aún no tenga recepciones.")
                session.execute(text("UPDATE supplier_purchases SET status='CANCELLED',updated_at=CURRENT_TIMESTAMP WHERE id=:id"), {"id":purchase_id})
                session.execute(text("INSERT INTO supplier_purchase_audit_events (purchase_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'CANCELLED',CAST(:fields AS JSONB))"), {"id":purchase_id,"actor":actor_id,"fields":json.dumps({"status":"CANCELLED"})})
            return self.get_purchase(purchase_id)
        except PurchaseConflict:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def receive_purchase(self, *, actor_id, purchase_id, idempotency_key: UUID, request_hash, values):
        try:
            replay = False
            with self._session_factory() as session, session.begin():
                prior = session.execute(text("SELECT id,request_hash FROM purchase_receipts WHERE purchase_id=:purchase AND actor_user_id=:actor AND idempotency_key=:key"), {"purchase":purchase_id,"actor":actor_id,"key":idempotency_key}).mappings().first()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise PurchaseConflict("La clave de idempotencia ya se usó con otros datos.")
                    receipt_id, replay = int(prior["id"]), True
                else:
                    purchase = session.execute(text("SELECT status FROM supplier_purchases WHERE id=:id FOR UPDATE"), {"id":purchase_id}).mappings().first()
                    if purchase is None:
                        raise PurchaseNotFound()
                    if purchase["status"] not in {"REGISTERED", "PARTIALLY_RECEIVED"}:
                        raise PurchaseConflict("La compra no admite nuevas recepciones.")
                    lines = session.execute(text("""SELECT i.id,i.quantity,i.spare_part_id,i.code_snapshot,i.description_snapshot,
                        coalesce((SELECT sum(ri.quantity_received) FROM purchase_receipt_items ri
                                  WHERE ri.purchase_item_id=i.id),0) AS received
                        FROM supplier_purchase_items i WHERE i.purchase_id=:id ORDER BY i.id FOR UPDATE"""), {"id":purchase_id}).mappings().all()
                    by_id = {int(line["id"]): line for line in lines}
                    incoming = {int(item["purchase_item_id"]): Decimal(item["quantity_received"]) for item in values["items"]}
                    if not incoming or set(incoming) - set(by_id):
                        raise PurchaseError("Una o más líneas no pertenecen a esta compra.", field="items")
                    outstanding = {}
                    for line_id, qty in incoming.items():
                        line = by_id[line_id]
                        remaining = Decimal(line["quantity"]) - Decimal(line["received"])
                        if qty > remaining:
                            raise PurchaseConflict("La cantidad recibida supera lo pendiente de la línea.")
                        outstanding[line_id] = remaining
                        if line["spare_part_id"] is not None and qty != qty.to_integral_value():
                            raise PurchaseError("El inventario admite cantidades recibidas enteras.", field="quantity_received")
                    receipt_id = session.execute(text("""INSERT INTO purchase_receipts
                        (purchase_id,actor_user_id,idempotency_key,request_hash,notes)
                        VALUES (:purchase,:actor,:key,:hash,:notes) RETURNING id"""), {
                        "purchase":purchase_id,"actor":actor_id,"key":idempotency_key,"hash":request_hash,"notes":values.get("notes")}).scalar_one()
                    received_totals = {line_id: Decimal(line["received"]) for line_id,line in by_id.items()}
                    received_totals.update({key: received_totals[key] + qty for key,qty in incoming.items()})
                    for line_id, qty in incoming.items():
                        line = by_id[line_id]
                        receipt_item_id = session.execute(text("INSERT INTO purchase_receipt_items (receipt_id,purchase_item_id,quantity_received) VALUES (:receipt,:line,:qty) RETURNING id"), {"receipt":receipt_id,"line":line_id,"qty":qty}).scalar_one()
                        if line["spare_part_id"] is not None:
                            part = session.execute(text("SELECT id,code,name,current_stock FROM spare_parts WHERE id=:id FOR UPDATE"), {"id":line["spare_part_id"]}).mappings().first()
                            if part is None:
                                raise PurchaseConflict("El repuesto de la línea ya no está disponible en el catálogo.")
                            stock_before, delta = int(part["current_stock"]), int(qty)
                            stock_after = stock_before + delta
                            if stock_after > 999999:
                                raise PurchaseConflict("La recepción excede el máximo de existencias permitido.")
                            session.execute(text("UPDATE spare_parts SET current_stock=:stock,updated_at=CURRENT_TIMESTAMP WHERE id=:id"), {"stock":stock_after,"id":part["id"]})
                            session.execute(text("""INSERT INTO inventory_movements
                                (spare_part_id,purchase_receipt_item_id,movement_type,code_snapshot,name_snapshot,
                                 quantity_delta,stock_before,stock_after,actor_user_id)
                                VALUES (:part,:receipt_item,'PURCHASE_RECEIPT',:code,:name,:delta,:before,:after,:actor)"""), {
                                "part":part["id"],"receipt_item":receipt_item_id,"code":line["code_snapshot"] or part["code"],
                                "name":part["name"],"delta":delta,
                                "before":stock_before,"after":stock_after,"actor":actor_id})
                    ordered_totals = {int(line["id"]): Decimal(line["quantity"]) for line in lines}
                    try:
                        new_status = next_receipt_status(purchase["status"], ordered_totals, received_totals)
                    except PurchaseConflictFailure as exc:
                        raise PurchaseConflict(str(exc)) from exc
                    session.execute(text("UPDATE supplier_purchases SET status=:status,updated_at=CURRENT_TIMESTAMP WHERE id=:id"), {"status":new_status,"id":purchase_id})
                    session.execute(text("INSERT INTO supplier_purchase_audit_events (purchase_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'RECEIPT_CONFIRMED',CAST(:fields AS JSONB))"), {"id":purchase_id,"actor":actor_id,"fields":json.dumps({"receipt_id":int(receipt_id),"status":new_status})})
            detail = self._receipt_detail(receipt_id)
            return detail, replay
        except (PurchaseError, SupplierNotFound):
            raise
        except IntegrityError as exc:
            with self._session_factory() as session:
                prior = session.execute(text("SELECT id,request_hash FROM purchase_receipts WHERE purchase_id=:purchase AND actor_user_id=:actor AND idempotency_key=:key"), {"purchase":purchase_id,"actor":actor_id,"key":idempotency_key}).mappings().first()
                if prior:
                    if prior["request_hash"] != request_hash:
                        raise PurchaseConflict("La clave de idempotencia ya se usó con otros datos.") from exc
                    return self._receipt_detail(int(prior["id"])), True
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def _receipt_detail(self, receipt_id):
        with self._session_factory() as session:
            row = session.execute(text("SELECT id,purchase_id,actor_user_id,received_at,notes FROM purchase_receipts WHERE id=:id"), {"id":receipt_id}).mappings().first()
            if row is None:
                return None
            items = session.execute(text("""SELECT ri.purchase_item_id,ri.quantity_received FROM purchase_receipt_items ri
                WHERE ri.receipt_id=:id ORDER BY ri.id"""), {"id":receipt_id}).mappings().all()
            return {"id":int(row["id"]),"purchase_id":int(row["purchase_id"]),"received_by":int(row["actor_user_id"]),
                    "received_at":_iso(row["received_at"]),"notes":row["notes"],
                    "items":[{"purchase_item_id":int(x["purchase_item_id"]),"quantity_received":str(x["quantity_received"])} for x in items]}

    def list_receipts(self, purchase_id):
        try:
            with self._session_factory() as session:
                exists = session.execute(text("SELECT 1 FROM supplier_purchases WHERE id=:id"), {"id":purchase_id}).first()
                if exists is None:
                    return None
                ids = session.execute(text("SELECT id FROM purchase_receipts WHERE purchase_id=:id ORDER BY received_at,id"), {"id":purchase_id}).scalars().all()
            return [self._receipt_detail(int(receipt_id)) for receipt_id in ids]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc
