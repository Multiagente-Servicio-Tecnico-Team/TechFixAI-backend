"""Transactional PostgreSQL persistence for direct-sale quotations and reservations."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.adapters.persistence.inventory_movements import apply_stock_movement

from app.database.connection import SessionLocal, get_engine
from app.domain.customer_commerce import available_stock
from app.domain.money import to_money


def _session_factory():
    get_engine()
    return SessionLocal


class SalesQuoteRepositoryAdapter:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _session_factory()

    def get_sales_quote(self, quote_id: int, *, customer_id: int | None = None):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT q.id,q.customer_id,q.quote_type::text AS kind,
                    q.ticket_id,q.status::text AS status,q.total_amount,q.expires_at,q.created_at,
                    q.customer_name_snapshot,q.customer_phone_snapshot,q.customer_email_snapshot,
                    p.status::text AS payment_status,r.status AS inventory_reservation_status
                FROM quotes q LEFT JOIN payments p ON p.quote_id=q.id
                  AND p.commercial_customer_id=q.customer_id
                LEFT JOIN inventory_reservations r ON r.quote_id=q.id
                WHERE q.id=:id AND q.quote_type='DIRECT_SALE'
                  AND (CAST(:customer AS bigint) IS NULL OR q.customer_id=CAST(:customer AS bigint))
                ORDER BY p.id DESC LIMIT 1"""), {"id": quote_id, "customer": customer_id}).mappings().first()
            if row is None:
                return None
            result = dict(row)
            result["inventory_reservation_status"] = result["inventory_reservation_status"] or "NOT_RESERVED"
            result["lines"] = [dict(line) for line in session.execute(text("""SELECT qd.spare_part_id,
                    COALESCE(qd.custom_item_name,sp.name,'Artículo') AS name_snapshot,sp.code AS code_snapshot,
                    qd.quantity,qd.unit_price,qd.subtotal FROM quote_details qd
                LEFT JOIN spare_parts sp ON sp.id=qd.spare_part_id WHERE qd.quote_id=:id ORDER BY qd.id"""),
                {"id": quote_id}).mappings()]
            result["audit_events"] = [dict(event) for event in session.execute(text("""SELECT actor_user_id,event_type,changed_fields,created_at
                FROM quote_audit_events WHERE quote_id=:id ORDER BY created_at,id"""), {"id": quote_id}).mappings()]
            return result

    def list_sales_quotes(self, *, customer_id: int | None = None, status: str | None = None,
                          limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            rows = session.execute(text("""SELECT q.id FROM quotes q WHERE q.quote_type='DIRECT_SALE'
                AND (CAST(:customer AS bigint) IS NULL OR q.customer_id=CAST(:customer AS bigint))
                AND (CAST(:status AS text) IS NULL OR q.status::text=CAST(:status AS text))
                ORDER BY q.created_at DESC,q.id DESC LIMIT :limit OFFSET :offset"""),
                {"customer": customer_id, "status": status, "limit": limit, "offset": offset}).scalars().all()
            return [self.get_sales_quote(int(row), customer_id=customer_id) for row in rows]

    def list_customer_quotes(self, *, customer_id: int, status: str | None = None,
                             limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            ids = session.execute(text("""SELECT id FROM quotes WHERE customer_id=:customer
                AND (CAST(:status AS text) IS NULL OR status::text=CAST(:status AS text))
                ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"""), {
                "customer": customer_id, "status": status, "limit": limit, "offset": offset,
            }).scalars().all()
        return [self.get_commercial_quote(int(quote_id), customer_id=customer_id) for quote_id in ids]

    def get_commercial_quote(self, quote_id: int, *, customer_id: int):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT q.id,q.customer_id,q.quote_type::text AS kind,q.ticket_id,
                    q.status::text AS status,q.total_amount,q.expires_at,q.created_at,q.observations,
                    p.status::text AS payment_status,r.status AS inventory_reservation_status
                FROM quotes q LEFT JOIN payments p ON p.quote_id=q.id AND p.commercial_customer_id=q.customer_id
                LEFT JOIN inventory_reservations r ON r.quote_id=q.id
                WHERE q.id=:id AND q.customer_id=:customer ORDER BY p.id DESC LIMIT 1"""),
                {"id": quote_id, "customer": customer_id}).mappings().first()
            if row is None:
                return None
            result = dict(row)
            result["inventory_reservation_status"] = result["inventory_reservation_status"] or "NOT_RESERVED"
            result["lines"] = [dict(line) for line in session.execute(text("""SELECT qd.spare_part_id,
                    COALESCE(qd.custom_item_name,sp.name,'Artículo') AS name_snapshot,sp.code AS code_snapshot,
                    qd.quantity,qd.unit_price,qd.subtotal FROM quote_details qd
                LEFT JOIN spare_parts sp ON sp.id=qd.spare_part_id WHERE qd.quote_id=:id ORDER BY qd.id"""),
                {"id": quote_id}).mappings()]
            return result

    def accept_service_quote(self, *, quote_id: int, customer_id: int, actor_user_id: int):
        with self._session_factory() as session, session.begin():
            quote = session.execute(text("""SELECT id,quote_type::text AS kind,status::text AS status,ticket_id
                FROM quotes WHERE id=:id AND customer_id=:customer FOR UPDATE"""),
                {"id": quote_id, "customer": customer_id}).mappings().first()
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            if quote["kind"] == "DIRECT_SALE" or quote["ticket_id"] is None:
                raise ValueError("La cotización no es de servicio.")
            if quote["status"] != "PENDING":
                raise ValueError("La cotización ya no está pendiente.")
            session.execute(text("UPDATE quotes SET status='ACCEPTED',accepted_by_user_id=:actor,accepted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                {"actor": actor_user_id, "id": quote_id})
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,'ACCEPTED','{"status":"ACCEPTED"}'::jsonb)"""),
                {"quote": quote_id, "actor": actor_user_id})
            return {"quote_id": quote_id, "status": "ACCEPTED"}

    def list_sales_orders(self, *, customer_id: int | None = None, limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            ids = session.execute(text("""SELECT id FROM sales_orders WHERE (CAST(:customer AS bigint) IS NULL OR customer_id=CAST(:customer AS bigint))
                ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"""), {
                "customer": customer_id, "limit": limit, "offset": offset,
            }).scalars().all()
        return [self.get_sales_order(int(order_id), customer_id=customer_id) for order_id in ids]

    def get_sales_order(self, order_id: int, *, customer_id: int | None = None):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT o.id,o.code,o.customer_id,o.quote_id,o.payment_id,o.status,
                    o.total_amount,o.created_at,p.status::text AS payment_status,p.payment_method::text AS payment_method,
                    p.transaction_reference,p.confirmed_at,p.confirmed_by_user_id
                FROM sales_orders o JOIN payments p ON p.id=o.payment_id
                WHERE o.id=:id AND (CAST(:customer AS bigint) IS NULL OR o.customer_id=CAST(:customer AS bigint))"""),
                {"id": order_id, "customer": customer_id}).mappings().first()
            if row is None:
                return None
            result = dict(row)
            result["items"] = [dict(item) for item in session.execute(text("""SELECT name_snapshot,code_snapshot,
                    quantity,unit_price,subtotal FROM sales_order_items WHERE sales_order_id=:id ORDER BY id"""),
                {"id": order_id}).mappings()]
            return result

    def list_customer_payments(self, *, customer_id: int, status: str | None = None,
                               limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            rows = session.execute(text("""SELECT id,quote_id,amount,status::text AS status,
                    payment_method::text AS payment_method,transaction_reference,created_at,confirmed_at
                FROM payments WHERE commercial_customer_id=:customer
                  AND (CAST(:status AS text) IS NULL OR status::text=CAST(:status AS text))
                ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset"""), {
                "customer": customer_id, "status": status, "limit": limit, "offset": offset,
            }).mappings().all()
            return [dict(row) for row in rows]

    def list_admin_payments(self, *, customer_id: int | None = None, status: str | None = None,
                            limit: int = 50, offset: int = 0):
        with self._session_factory() as session:
            rows = session.execute(text("""SELECT p.id,p.payment_code,p.ticket_id,p.quote_id,p.commercial_customer_id AS customer_id,
                    p.amount,p.status::text AS status,p.payment_method::text AS payment_method,
                    p.transaction_reference,p.created_at,p.confirmed_at,p.confirmed_by_user_id,
                    c.display_name AS customer_name
                FROM payments p LEFT JOIN customers c ON c.id=p.commercial_customer_id
                WHERE p.commercial_customer_id IS NOT NULL
                  AND (CAST(:customer AS bigint) IS NULL OR p.commercial_customer_id=CAST(:customer AS bigint))
                  AND (CAST(:status AS text) IS NULL OR p.status::text=CAST(:status AS text))
                ORDER BY p.created_at DESC,p.id DESC LIMIT :limit OFFSET :offset"""), {
                "customer": customer_id, "status": status, "limit": limit, "offset": offset,
            }).mappings().all()
            return [dict(row) for row in rows]

    def resolve_direct_sales_quote(self, *, quote_id: int, customer_id: int | None,
                                   actor_user_id: int | None, target_status: str,
                                   notes: str | None = None):
        if target_status not in {"REJECTED", "CANCELLED"}:
            raise ValueError("La transición solicitada no está permitida.")
        with self._session_factory() as session, session.begin():
            quote = session.execute(text("""SELECT q.id,q.customer_id,c.user_id,q.quote_type::text AS kind,q.status::text AS status
                FROM quotes q JOIN customers c ON c.id=q.customer_id WHERE q.id=:id FOR UPDATE OF q"""),
                {"id": quote_id}).mappings().first()
            if quote is None or quote["kind"] != "DIRECT_SALE" or (customer_id is not None and int(quote["customer_id"] or 0) != customer_id):
                raise LookupError("Cotización no encontrada.")
            actor_user_id = actor_user_id or quote["user_id"]
            if actor_user_id is None:
                raise PermissionError("Una cuenta autenticada debe registrar el cambio de estado.")
            if quote["status"] not in {"PENDING", "ACCEPTED"}:
                raise ValueError("La cotización ya fue resuelta.")
            reservation = session.execute(text("SELECT * FROM inventory_reservations WHERE quote_id=:id FOR UPDATE"), {"id": quote_id}).mappings().first()
            if reservation is not None and reservation["status"] == "RESERVED":
                session.execute(text("""UPDATE inventory_reservations SET status='RELEASED',released_at=CURRENT_TIMESTAMP,
                    released_by_user_id=:actor,release_reason=:reason WHERE id=:id"""), {
                    "actor": actor_user_id, "reason": target_status, "id": reservation["id"],
                })
            session.execute(text("UPDATE quotes SET status=:status,updated_at=CURRENT_TIMESTAMP WHERE id=:id"),
                {"status": target_status, "id": quote_id})
            if quote["status"] == "ACCEPTED":
                session.execute(text("""UPDATE payments SET status='FAILED',notes=COALESCE(:notes,'Cotización resuelta sin pago.'),updated_at=CURRENT_TIMESTAMP
                    WHERE quote_id=:quote AND status='PENDING'"""), {"notes": notes, "quote": quote_id})
            import json
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,:event,CAST(:fields AS jsonb))"""), {
                "quote": quote_id, "actor": actor_user_id, "event": target_status,
                "fields": json.dumps({"status": target_status, "notes": notes, "reservation": "RELEASED"}),
            })
            return {"quote_id": quote_id, "status": target_status,
                    "reservation_status": "RELEASED" if reservation else "NOT_RESERVED"}

    def create_direct_sales_quote(
        self, *, customer_id: int, actor_user_id: int | None, lines: list[dict[str, int]],
        expires_at: datetime, observations: str | None = None, origin: str = "MANUAL",
    ) -> dict[str, Any]:
        if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc):
            raise ValueError("La fecha de vencimiento debe ser futura e incluir zona horaria.")
        if not lines or len(lines) > 50:
            raise ValueError("La cotización requiere entre 1 y 50 artículos.")
        quantities: dict[int, int] = {}
        for line in lines:
            part_id, quantity = line.get("spare_part_id"), line.get("quantity")
            if type(part_id) is not int or part_id < 1 or type(quantity) is not int or quantity < 1:
                raise ValueError("Cada artículo requiere identificador y cantidad positivos.")
            quantities[part_id] = quantities.get(part_id, 0) + quantity

        with self._session_factory() as session, session.begin():
            if origin not in {"MANUAL", "PORTAL", "CHAT"}:
                raise ValueError("El origen de la cotización no es válido.")
            customer = session.execute(text("""SELECT id,display_name,phone,email,user_id FROM customers
                WHERE id=:id AND active IS TRUE FOR SHARE"""), {"id": customer_id}).mappings().first()
            if customer is None:
                raise LookupError("El cliente comercial no existe o está inactivo.")
            actor_user_id = actor_user_id or customer["user_id"]
            if actor_user_id is None:
                raise ValueError("La creación de una cotización requiere una cuenta responsable.")
            parts: dict[int, dict[str, Any]] = {}
            for part_id in sorted(quantities):
                row = session.execute(text("""SELECT id,code,name,unit_price,current_stock,active
                    FROM spare_parts WHERE id=:id FOR UPDATE"""), {"id": part_id}).mappings().first()
                if row is None or not row["active"]:
                    raise LookupError(f"El artículo {part_id} no existe o está inactivo.")
                active = session.execute(text("""SELECT COALESCE(SUM(ri.quantity),0)
                    FROM inventory_reservation_items ri JOIN inventory_reservations r ON r.id=ri.reservation_id
                    WHERE ri.spare_part_id=:part AND r.status='RESERVED' AND r.expires_at>:now"""),
                    {"part": part_id, "now": datetime.now(timezone.utc)}).scalar_one()
                if available_stock(int(row["current_stock"]), int(active)) < quantities[part_id]:
                    raise ValueError(f"Stock insuficiente para {row['name']}.")
                parts[part_id] = dict(row)

            priced_lines = []
            total = Decimal("0.00")
            for part_id in sorted(quantities):
                part, quantity = parts[part_id], quantities[part_id]
                price = to_money(part["unit_price"])
                subtotal = to_money(price * quantity)
                total += subtotal
                priced_lines.append((part, quantity, price, subtotal))
            total = to_money(total)
            if total <= 0 or total > Decimal("99999999.99"):
                raise ValueError("El importe total excede el límite admitido por el sistema.")
            quote_id = int(session.execute(text("""INSERT INTO quotes
                (ticket_id,customer_id,quote_type,labor_cost,parts_cost,total_amount,status,observations,
                 origin,created_by_user_id,expires_at,customer_name_snapshot,customer_phone_snapshot,customer_email_snapshot)
                VALUES (NULL,:customer,'DIRECT_SALE',0,:total,:total,'PENDING',:observations,
                        :origin,:actor,:expires,:name,:phone,:email) RETURNING id"""), {
                "customer": customer_id, "total": total, "observations": observations,
                "actor": actor_user_id, "expires": expires_at, "name": customer["display_name"],
                "phone": customer["phone"], "email": customer["email"], "origin": origin,
            }).scalar_one())
            for part, quantity, price, subtotal in priced_lines:
                session.execute(text("""INSERT INTO quote_details
                    (quote_id,spare_part_id,custom_item_name,quantity,unit_price,subtotal)
                    VALUES (:quote,:part,NULL,:quantity,:price,:subtotal)"""), {
                    "quote": quote_id, "part": part["id"], "quantity": quantity,
                    "price": price, "subtotal": subtotal,
                })
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,'CREATED',CAST(:fields AS jsonb))"""), {
                "quote": quote_id, "actor": actor_user_id,
                "fields": '{"kind":"DIRECT_SALE","status":"PENDING"}',
            })
            return {"id": quote_id, "customer_id": customer_id, "kind": "DIRECT_SALE",
                    "ticket_id": None, "status": "PENDING", "total_amount": total,
                    "payment_status": None, "inventory_reservation_status": "NOT_RESERVED",
                    "created_at": datetime.now(timezone.utc), "expires_at": expires_at, "lines": [
                        {"spare_part_id": int(p["id"]), "name_snapshot": p["name"],
                         "code_snapshot": p["code"], "quantity": q,
                         "unit_price": price, "subtotal": subtotal}
                        for p, q, price, subtotal in priced_lines]}

    def accept_direct_sales_quote(
        self, *, quote_id: int, customer_id: int, actor_user_id: int | None,
        idempotency_key: str, confirmation_channel: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session, session.begin():
            quote = session.execute(text("""SELECT q.id,q.customer_id,c.user_id,q.quote_type::text AS kind,q.status::text AS status,
                    q.ticket_id,q.total_amount,q.expires_at FROM quotes q JOIN customers c ON c.id=q.customer_id
                    WHERE q.id=:id FOR UPDATE OF q"""),
                {"id": quote_id}).mappings().first()
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            if int(quote["customer_id"] or 0) != customer_id:
                raise PermissionError("La cotización no pertenece al cliente autenticado.")
            actor_user_id = actor_user_id or quote["user_id"]
            if actor_user_id is None:
                raise PermissionError("Una cuenta autenticada debe registrar la aceptación.")
            if quote["kind"] != "DIRECT_SALE" or quote["ticket_id"] is not None:
                raise ValueError("Solo se pueden aceptar cotizaciones de venta directa.")
            existing = session.execute(text("SELECT id,status,expires_at FROM inventory_reservations WHERE quote_id=:quote FOR UPDATE"),
                {"quote": quote_id}).mappings().first()
            if quote["expires_at"] is None or quote["expires_at"].tzinfo is None or quote["expires_at"] <= now:
                if existing and existing["status"] == "RESERVED":
                    session.execute(text("""UPDATE inventory_reservations SET status='RELEASED',released_at=:now,
                        released_by_user_id=:actor,release_reason='EXPIRED' WHERE id=:id"""), {
                        "now": now, "actor": actor_user_id, "id": existing["id"],
                    })
                    session.execute(text("UPDATE payments SET status='FAILED',notes='Cotización vencida.',updated_at=:now WHERE quote_id=:quote AND status='PENDING'"),
                        {"now": now, "quote": quote_id})
                session.execute(text("UPDATE quotes SET status='EXPIRED',updated_at=:now WHERE id=:id AND status IN ('PENDING','ACCEPTED')"),
                    {"now": now, "id": quote_id})
                session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                    VALUES (:quote,:actor,'EXPIRED',CAST(:fields AS jsonb))"""), {
                    "quote": quote_id, "actor": actor_user_id,
                    "fields": '{"status":"EXPIRED","reservation":"RELEASED"}',
                })
                return {"quote_id": quote_id, "status": "EXPIRED", "error": "La cotización venció y no puede aceptarse."}
            if quote["status"] == "ACCEPTED" and existing and existing["status"] == "RESERVED":
                if existing["idempotency_key"] != idempotency_key:
                    raise ValueError("La cotización ya fue aceptada con otra clave de idempotencia.")
                payment = session.execute(text("SELECT id,payment_code FROM payments WHERE quote_id=:quote AND commercial_customer_id=:customer ORDER BY id DESC LIMIT 1"),
                    {"quote": quote_id, "customer": customer_id}).mappings().first()
                return {"quote_id": quote_id, "status": "ACCEPTED", "reservation_status": "RESERVED",
                        "expires_at": existing["expires_at"], "idempotent_replay": True,
                        "payment_id": payment["id"] if payment else None,
                        "payment_code": payment["payment_code"] if payment else None}
            if quote["status"] != "PENDING":
                raise ValueError("La cotización ya no está pendiente.")
            details = session.execute(text("""SELECT qd.id AS quote_detail_id,qd.spare_part_id,qd.quantity,
                    qd.unit_price,qd.subtotal,sp.code,sp.name,sp.current_stock,sp.active
                FROM quote_details qd JOIN spare_parts sp ON sp.id=qd.spare_part_id
                WHERE qd.quote_id=:quote ORDER BY qd.spare_part_id,qd.id"""),
                {"quote": quote_id}).mappings().all()
            if not details:
                raise ValueError("La cotización no contiene artículos de inventario.")
            part_ids = sorted({int(row["spare_part_id"]) for row in details})
            locked_parts = {}
            for part_id in part_ids:
                part = session.execute(text("SELECT id,code,name,current_stock,active FROM spare_parts WHERE id=:id FOR UPDATE"),
                    {"id": part_id}).mappings().one()
                locked_parts[part_id] = part
            for row in details:
                part = locked_parts[int(row["spare_part_id"])]
                reserved = int(session.execute(text("""SELECT COALESCE(SUM(ri.quantity),0)
                    FROM inventory_reservation_items ri JOIN inventory_reservations r ON r.id=ri.reservation_id
                    WHERE ri.spare_part_id=:part AND r.status='RESERVED' AND r.expires_at>:now"""),
                    {"part": row["spare_part_id"], "now": now}).scalar_one())
                if not part["active"] or available_stock(int(part["current_stock"]), reserved) < int(row["quantity"]):
                    raise ValueError(f"Stock insuficiente para {part['name']}; no se reservó ningún artículo.")
            reservation_id = int(session.execute(text("""INSERT INTO inventory_reservations
                (quote_id,customer_id,idempotency_key,status,expires_at,accepted_by_user_id,accepted_at)
                VALUES (:quote,:customer,:key,'RESERVED',:expires,:actor,:now) RETURNING id"""), {
                "quote": quote_id, "customer": customer_id, "expires": quote["expires_at"],
                "actor": actor_user_id, "now": now, "key": idempotency_key,
            }).scalar_one())
            for row in details:
                part = locked_parts[int(row["spare_part_id"])]
                session.execute(text("""INSERT INTO inventory_reservation_items
                    (reservation_id,quote_detail_id,spare_part_id,code_snapshot,name_snapshot,quantity,unit_price,subtotal)
                    VALUES (:reservation,:detail,:part,:code,:name,:quantity,:price,:subtotal)"""), {
                    "reservation": reservation_id, "detail": row["quote_detail_id"],
                    "part": row["spare_part_id"], "code": part["code"], "name": part["name"],
                    "quantity": row["quantity"], "price": row["unit_price"], "subtotal": row["subtotal"],
                })
            session.execute(text("UPDATE quotes SET status='ACCEPTED',accepted_by_user_id=:actor,accepted_at=:now,updated_at=:now WHERE id=:id"),
                {"actor": actor_user_id, "now": now, "id": quote_id})
            payment = session.execute(text("""INSERT INTO payments
                (ticket_id,quote_id,customer_id,commercial_customer_id,payment_code,amount,status)
                VALUES (NULL,:quote,NULL,:customer,:code,:amount,'PENDING') RETURNING id,payment_code"""), {
                "quote": quote_id, "customer": customer_id, "code": f"PAY-{uuid4().hex[:16].upper()}",
                "amount": quote["total_amount"],
            }).mappings().one()
            fields = '{"status":"ACCEPTED","reservation":"RESERVED"}'
            if confirmation_channel:
                import json
                fields = json.dumps({"status": "ACCEPTED", "reservation": "RESERVED",
                                     "confirmation_channel": confirmation_channel, "notes": notes})
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,'ACCEPTED',CAST(:fields AS jsonb))"""), {
                "quote": quote_id, "actor": actor_user_id, "fields": fields,
            })
            return {"quote_id": quote_id, "status": "ACCEPTED", "reservation_status": "RESERVED",
                    "expires_at": quote["expires_at"], "idempotent_replay": False,
                    "payment_id": int(payment["id"]), "payment_code": payment["payment_code"]}

    def confirm_direct_sales_payment(
        self, *, quote_id: int, actor_user_id: int, idempotency_key: str,
        method: str, transaction_reference: str | None, notes: str | None,
    ) -> dict[str, Any]:
        if method not in {"CREDIT_CARD", "DEBIT_CARD", "BANK_TRANSFER", "CASH", "PAYMENT_GATEWAY"}:
            raise ValueError("El método de pago no es válido.")
        now = datetime.now(timezone.utc)
        with self._session_factory() as session, session.begin():
            quote = session.execute(text("""SELECT q.*,q.quote_type::text AS kind,q.status::text AS quote_status,
                    c.display_name,c.phone,c.email
                FROM quotes q JOIN customers c ON c.id=q.customer_id WHERE q.id=:id FOR UPDATE OF q"""),
                {"id": quote_id}).mappings().first()
            if quote is None:
                raise LookupError("Cotización no encontrada.")
            order = session.execute(text("SELECT id,code,status,total_amount,customer_id,quote_id,payment_id,created_at FROM sales_orders WHERE quote_id=:id"),
                {"id": quote_id}).mappings().first()
            if order is not None:
                payment = session.execute(text("SELECT idempotency_key FROM payments WHERE id=:id"), {"id": order["payment_id"]}).scalar_one()
                if payment == idempotency_key:
                    return dict(order)
                raise ValueError("La venta de esta cotización ya fue confirmada con otra clave.")
            if quote["kind"] != "DIRECT_SALE" or quote["quote_status"] != "ACCEPTED":
                raise ValueError("Solo una cotización de venta aceptada puede pagarse.")
            reservation = session.execute(text("SELECT * FROM inventory_reservations WHERE quote_id=:id FOR UPDATE"), {"id": quote_id}).mappings().first()
            if reservation is None or reservation["status"] != "RESERVED" or reservation["expires_at"] <= now:
                if reservation is not None and reservation["status"] == "RESERVED":
                    session.execute(text("""UPDATE inventory_reservations SET status='RELEASED',released_at=:now,
                        released_by_user_id=:actor,release_reason='EXPIRED' WHERE id=:id"""), {
                        "now": now, "actor": actor_user_id, "id": reservation["id"],
                    })
                    session.execute(text("UPDATE quotes SET status='EXPIRED',updated_at=:now WHERE id=:id"), {"now": now, "id": quote_id})
                    session.execute(text("UPDATE payments SET status='FAILED',notes='Reserva vencida antes de confirmar pago.',updated_at=:now WHERE quote_id=:quote AND status='PENDING'"), {"now": now, "quote": quote_id})
                    session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                        VALUES (:quote,:actor,'EXPIRED','{"reservation":"RELEASED","payment_status":"FAILED"}'::jsonb)"""),
                        {"quote": quote_id, "actor": actor_user_id})
                    return {"quote_id": quote_id, "status": "EXPIRED", "error": "La reserva venció antes de confirmar el pago."}
                raise ValueError("La reserva no existe o ya fue resuelta.")
            payment = session.execute(text("SELECT * FROM payments WHERE quote_id=:id AND commercial_customer_id=:customer ORDER BY id DESC LIMIT 1 FOR UPDATE"),
                {"id": quote_id, "customer": quote["customer_id"]}).mappings().first()
            if payment is None or payment["status"] != "PENDING":
                raise ValueError("No existe un pago pendiente para esta cotización.")
            session.execute(text("""UPDATE payments SET status='COMPLETED',payment_method=CAST(:method AS payment_method_enum),
                transaction_reference=:reference,notes=:notes,confirmed_by_user_id=:actor,confirmed_at=:now,
                idempotency_key=:key,updated_at=:now WHERE id=:id"""), {
                "method": method, "reference": transaction_reference, "notes": notes,
                "actor": actor_user_id, "now": now, "key": idempotency_key, "id": payment["id"],
            })
            code = f"SLS-{uuid4().hex[:12].upper()}"
            order_id = int(session.execute(text("""INSERT INTO sales_orders
                (code,quote_id,payment_id,customer_id,status,total_amount,customer_name_snapshot,
                 customer_phone_snapshot,customer_email_snapshot,created_by_user_id)
                VALUES (:code,:quote,:payment,:customer,'PAID',:total,:name,:phone,:email,:actor) RETURNING id"""), {
                "code": code, "quote": quote_id, "payment": payment["id"],
                "customer": quote["customer_id"], "total": quote["total_amount"],
                "name": quote["customer_name_snapshot"] or quote["display_name"],
                "phone": quote["customer_phone_snapshot"] or quote["phone"],
                "email": quote["customer_email_snapshot"] or quote["email"], "actor": actor_user_id,
            }).scalar_one())
            reserved_lines = session.execute(text("""SELECT ri.*,sp.current_stock FROM inventory_reservation_items ri
                JOIN spare_parts sp ON sp.id=ri.spare_part_id WHERE ri.reservation_id=:id ORDER BY ri.spare_part_id,ri.id"""),
                {"id": reservation["id"]}).mappings().all()
            # The reservation is consumed in this transaction before the common
            # movement writer checks that the remaining stock covers other holds.
            session.execute(text("UPDATE inventory_reservations SET status='CONSUMED',consumed_at=:now WHERE id=:id"),
                {"now": now, "id": reservation["id"]})
            for line in reserved_lines:
                line_id = int(session.execute(text("""INSERT INTO sales_order_items
                    (sales_order_id,quote_detail_id,spare_part_id,code_snapshot,name_snapshot,quantity,unit_price,subtotal)
                    VALUES (:order,:detail,:part,:code,:name,:quantity,:price,:subtotal) RETURNING id"""), {
                    "order": order_id, "detail": line["quote_detail_id"], "part": line["spare_part_id"],
                    "code": line["code_snapshot"], "name": line["name_snapshot"],
                    "quantity": line["quantity"], "price": line["unit_price"], "subtotal": line["subtotal"],
                }).scalar_one())
                try:
                    apply_stock_movement(session, part_id=int(line["spare_part_id"]), quantity_delta=-int(line["quantity"]),
                        movement_type="SALE", actor_user_id=actor_user_id, sales_order_item_id=line_id,
                        code_snapshot=line["code_snapshot"], name_snapshot=line["name_snapshot"], now=now)
                except ValueError as exc:
                    raise ValueError("El stock físico cambió o hay reservas que impiden confirmar la venta.") from exc
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,'PAYMENT_CONFIRMED',CAST(:fields AS jsonb))"""), {
                "quote": quote_id, "actor": actor_user_id,
                "fields": '{"payment_status":"COMPLETED","order_status":"PAID","reservation":"CONSUMED"}',
            })
            result = session.execute(text("SELECT id,code,status,total_amount,customer_id,quote_id,payment_id,created_at FROM sales_orders WHERE id=:id"), {"id": order_id}).mappings().one()
            return dict(result)
