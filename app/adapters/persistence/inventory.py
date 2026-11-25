"""Adaptador PostgreSQL para el CRUD administrativo del catálogo."""
import logging
import hashlib
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.errors import InventoryConflict, InventoryNotFound, InventoryStorageUnavailable
from app.domain.inventory import InventoryPart, InventoryPartDraft
from app.adapters.persistence.inventory_movements import apply_stock_movement, movement_to_dict

logger = logging.getLogger(__name__)

PART_COLUMNS = """
    id, code, name, category, description, unit_price, current_stock,
    minimum_threshold, active, created_at, updated_at
"""


def _reserved_units(session, part_id: int) -> int:
    # Keep existing inventory CRUD functional during the additive-migration window.
    # No reservation can exist until the new table exists; after migration the
    # transactional sum becomes authoritative.
    if not inspect(session.connection()).has_table("inventory_reservations", schema="public" if session.bind.dialect.name == "postgresql" else None):
        return 0
    return int(session.execute(text("""SELECT COALESCE(SUM(ri.quantity),0)
        FROM inventory_reservation_items ri JOIN inventory_reservations r ON r.id=ri.reservation_id
        WHERE ri.spare_part_id=:part AND r.status='RESERVED' AND r.expires_at>CURRENT_TIMESTAMP"""),
        {"part": part_id}).scalar_one())


def _row_lock_clause(session) -> str:
    return " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""


def _default_session_factory():
    from app.database.connection import SessionLocal, get_engine

    get_engine()
    return SessionLocal


class InventoryRepositoryAdapter:
    def __init__(self, session_factory=None):
        self._session_factory = session_factory or _default_session_factory()

    @staticmethod
    def _storage_error(exc: Exception) -> InventoryStorageUnavailable:
        logger.error("Inventory persistence failed: %s", type(exc).__name__)
        return InventoryStorageUnavailable()

    @staticmethod
    def _part(row: Any) -> InventoryPart:
        return InventoryPart(
            id=int(row["id"]),
            code=str(row["code"]),
            name=str(row["name"]),
            category=row["category"],
            description=row["description"],
            unit_price=Decimal(str(row["unit_price"])),
            current_stock=int(row["current_stock"]),
            minimum_threshold=int(row["minimum_threshold"]),
            active=bool(row["active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_parts(self) -> list[InventoryPart]:
        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text(f"SELECT {PART_COLUMNS} FROM spare_parts WHERE active IS TRUE ORDER BY name, code")
                ).mappings().all()
            return [self._part(row) for row in rows]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def list_categories(self) -> list[str]:
        try:
            with self._session_factory() as session:
                rows = session.execute(
                    text("""SELECT DISTINCT category FROM spare_parts
                            WHERE active IS TRUE AND category IS NOT NULL AND TRIM(category) <> ''
                            ORDER BY category""")
                ).scalars().all()
            return [str(value) for value in rows]
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def create_part(self, part: InventoryPartDraft, *, actor_id: int) -> InventoryPart:
        try:
            with self._session_factory() as session, session.begin():
                values = self._values(part)
                requested_stock = values.pop("current_stock", None)
                row = session.execute(
                    text("""INSERT INTO spare_parts
                            (code, name, category, description, unit_price, current_stock,
                             minimum_threshold, active)
                            VALUES (:code, :name, :category, :description, :unit_price,
                                    0, :minimum_threshold, TRUE)
                            RETURNING id, code, name, category, description, unit_price,
                                      current_stock, minimum_threshold, active, created_at, updated_at"""),
                    values,
                ).mappings().one()
                if requested_stock is not None and requested_stock > 0:
                    key = uuid4()
                    digest = hashlib.sha256(f"legacy-create:{row['id']}:{requested_stock}".encode()).hexdigest()
                    apply_stock_movement(session, part_id=int(row["id"]), quantity_delta=requested_stock,
                        movement_type="OPENING_BALANCE", actor_user_id=actor_id,
                        reason="Saldo inicial informado mediante el formulario anterior del inventario",
                        idempotency_key=key, request_hash=digest)
                    row = session.execute(text(f"SELECT {PART_COLUMNS} FROM spare_parts WHERE id=:id"), {"id": row["id"]}).mappings().one()
            return self._part(row)
        except IntegrityError as exc:
            if self._is_code_unique_error(exc):
                raise InventoryConflict(
                    "Ya existe un repuesto con ese código.", code="duplicate", field="code"
                ) from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_part(self, code: str, part: InventoryPartDraft, *, actor_id: int) -> InventoryPart | None:
        try:
            with self._session_factory() as session, session.begin():
                current = session.execute(
                    text("SELECT id,current_stock FROM spare_parts WHERE code=:code AND active IS TRUE" + _row_lock_clause(session)),
                    {"code": code},
                ).mappings().first()
                if current is None:
                    return None
                values = self._values(part)
                requested_stock = values.pop("current_stock", None)
                row = session.execute(
                    text("""UPDATE spare_parts
                            SET name = :name, category = :category, description = :description,
                                unit_price = :unit_price,
                                minimum_threshold = :minimum_threshold
                            WHERE code = :lookup_code AND active IS TRUE
                            RETURNING id, code, name, category, description, unit_price,
                                      current_stock, minimum_threshold, active, created_at, updated_at"""),
                    {**values, "lookup_code": code},
                ).mappings().first()
                if row and requested_stock is not None:
                    self._apply_count(session, int(current["id"]), requested_stock, actor_id,
                        "Ajuste de conteo informado mediante el formulario anterior del inventario")
                    row = session.execute(text(f"SELECT {PART_COLUMNS} FROM spare_parts WHERE id=:id"), {"id": current["id"]}).mappings().one()
            return self._part(row) if row else None
        except IntegrityError as exc:
            if self._is_code_unique_error(exc):
                raise InventoryConflict(
                    "Ya existe un repuesto con ese código.", code="duplicate", field="code"
                ) from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def delete_part(self, code: str) -> bool:
        try:
            with self._session_factory() as session, session.begin():
                current = session.execute(
                    text("SELECT id FROM spare_parts WHERE code=:code" + _row_lock_clause(session)),
                    {"code": code},
                ).mappings().first()
                if current is None:
                    return False
                reserved = _reserved_units(session, int(current["id"]))
                if reserved:
                    raise InventoryConflict(
                        "No se puede eliminar un artículo con unidades reservadas.",
                        code="reserved_stock",
                    )
                has_history = session.execute(text("SELECT EXISTS(SELECT 1 FROM inventory_movements WHERE spare_part_id=:id)"), {"id": current["id"]}).scalar_one()
                if has_history:
                    row = session.execute(text("UPDATE spare_parts SET active=FALSE,updated_at=CURRENT_TIMESTAMP WHERE code=:code RETURNING id"), {"code": code}).first()
                else:
                    row = session.execute(text("DELETE FROM spare_parts WHERE code=:code RETURNING id"), {"code": code}).first()
            return row is not None
        except IntegrityError as exc:
            if self._is_quote_reference_error(exc):
                raise InventoryConflict(
                    "No se puede eliminar porque el repuesto figura en presupuestos.",
                    code="in_use",
                ) from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    @staticmethod
    def _values(part: InventoryPartDraft) -> dict[str, object]:
        return {
            "code": part.code,
            "name": part.name,
            "category": part.category,
            "description": part.description,
            "unit_price": part.unit_price,
            "current_stock": part.current_stock,
            "minimum_threshold": part.minimum_threshold,
        }

    def record_opening_balance(self, *, part_id, count, actor_id, reason, idempotency_key, request_hash):
        return self._record_count(part_id=part_id, count=count, actor_id=actor_id, reason=reason,
            idempotency_key=idempotency_key, request_hash=request_hash, opening=True)

    def adjust_stock(self, *, part_id, count, actor_id, reason, idempotency_key, request_hash,
                     expected_stock=None):
        return self._record_count(part_id=part_id, count=count, actor_id=actor_id, reason=reason,
            idempotency_key=idempotency_key, request_hash=request_hash, opening=False,
            expected_stock=expected_stock)

    def _record_count(self, *, part_id, count, actor_id, reason, idempotency_key, request_hash,
                      opening, expected_stock=None):
        from app.application.errors import InventoryIdempotencyConflict, InventoryNotFound
        try:
            with self._session_factory() as session, session.begin():
                part = session.execute(text("SELECT id,code,current_stock FROM spare_parts WHERE id=:id AND active IS TRUE" + _row_lock_clause(session)), {"id": part_id}).mappings().first()
                if not part:
                    raise InventoryNotFound()
                # Serialize retries by item first; after waiting on this lock, a
                # concurrent request can see the winner's committed idempotency row.
                prior = session.execute(text("SELECT * FROM inventory_movements WHERE actor_user_id=:actor AND idempotency_key=:key AND actor_kind='USER'"),
                    {"actor": actor_id, "key": idempotency_key}).mappings().first()
                if prior:
                    if str(prior["request_hash"]).strip() != request_hash:
                        raise InventoryIdempotencyConflict()
                    return {"part": {"id": part_id, "code": prior["code_snapshot"], "current_stock": int(prior["stock_after"])},
                            "changed": True, "movement": movement_to_dict(prior), "replayed": True}
                before = int(part["current_stock"])
                if expected_stock is not None and before != expected_stock:
                    raise InventoryConflict(
                        "El stock cambió desde que se mostró la propuesta. Revísalo y formula de nuevo la operación.",
                        code="stock_changed",
                    )
                if opening and before != 0:
                    raise InventoryConflict("El saldo inicial ya fue establecido.", code="opening_exists")
                delta = int(count) - before
                if delta == 0:
                    return {"part": {"id": part_id, "code": part["code"], "current_stock": before}, "changed": False, "movement": None, "replayed": False}
                result = apply_stock_movement(session, part_id=int(part["id"]), quantity_delta=delta,
                    movement_type=("OPENING_BALANCE" if opening else ("ADJUSTMENT_IN" if delta > 0 else "ADJUSTMENT_OUT")),
                    actor_user_id=actor_id, reason=reason, idempotency_key=str(idempotency_key), request_hash=request_hash)
                return {"part": {"id": part_id, "code": result["code_snapshot"], "current_stock": int(result["stock_after"])},
                        "changed": True, "movement": movement_to_dict(result), "replayed": False}
        except (InventoryConflict, InventoryNotFound, InventoryIdempotencyConflict):
            raise
        except IntegrityError as exc:
            raise InventoryIdempotencyConflict() from exc
        except ValueError as exc:
            message = str(exc)
            code = "reserved_stock" if "reserv" in message.lower() else "invalid_stock_movement"
            raise InventoryConflict(message, code=code) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def _apply_count(self, session, part_id, count, actor_id, reason):
        part = session.execute(text("SELECT current_stock FROM spare_parts WHERE id=:id" + _row_lock_clause(session)), {"id": part_id}).mappings().one()
        delta = int(count) - int(part["current_stock"])
        if delta:
            key = uuid4()
            digest = hashlib.sha256(f"legacy-update:{part_id}:{count}".encode()).hexdigest()
            apply_stock_movement(session, part_id=part_id, quantity_delta=delta,
                movement_type="ADJUSTMENT_IN" if delta > 0 else "ADJUSTMENT_OUT", actor_user_id=actor_id,
                reason=reason, idempotency_key=key, request_hash=digest)

    def list_movements(self, *, part_id, limit=50, offset=0, movement_type=None, from_date=None, to_date=None):
        try:
            with self._session_factory() as session:
                if not session.execute(text("SELECT 1 FROM spare_parts WHERE id=:id"), {"id": part_id}).first():
                    from app.application.errors import InventoryNotFound
                    raise InventoryNotFound()
                clauses = ["im.spare_part_id=:part"]
                params = {"part": part_id, "limit": limit, "offset": offset}
                if movement_type:
                    clauses.append("im.movement_type=:type"); params["type"] = movement_type
                if from_date:
                    clauses.append("im.created_at>=:from_date"); params["from_date"] = from_date
                if to_date:
                    clauses.append("im.created_at<(CAST(:to_date AS date) + INTERVAL '1 day')"); params["to_date"] = to_date
                where = " AND ".join(clauses)
                count_params = {key: value for key, value in params.items() if key not in {"limit", "offset"}}
                total = int(session.execute(text(f"SELECT count(*) FROM inventory_movements im WHERE {where}"), count_params).scalar_one())
                rows = session.execute(text(f"""SELECT im.*, u.name AS actor_name,
                    EXISTS(SELECT 1 FROM inventory_movements cut WHERE cut.spare_part_id=im.spare_part_id
                      AND cut.movement_type='OPENING_BALANCE' AND cut.actor_kind='SYSTEM' AND im.id<cut.id) AS is_before_cutover
                    FROM inventory_movements im LEFT JOIN users u ON u.id=im.actor_user_id
                    WHERE {where} ORDER BY im.created_at DESC, im.id DESC LIMIT :limit OFFSET :offset"""), params).mappings().all()
            return {"items": [movement_to_dict(row, actor_name=row.get("actor_name"), is_before_cutover=row.get("is_before_cutover", False)) for row in rows],
                    "total": total, "limit": limit, "offset": offset}
        except InventoryNotFound:
            raise
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    @staticmethod
    def _is_code_unique_error(exc: IntegrityError) -> bool:
        message = str(getattr(exc, "orig", exc)).lower()
        return (
            "spare_parts.code" in message
            or "spare_parts_code_key" in message
            or "uq_spare_parts_code" in message
        )

    @staticmethod
    def _is_quote_reference_error(exc: IntegrityError) -> bool:
        message = str(getattr(exc, "orig", exc)).lower()
        # PostgreSQL includes the named referencing constraint; SQLite reports only
        # the generic FK message used by the isolated API integration fixture.
        return (
            ("quote_details" in message and ("spare_part_id" in message or "foreign key" in message))
            or "foreign key constraint failed" in message
        )
