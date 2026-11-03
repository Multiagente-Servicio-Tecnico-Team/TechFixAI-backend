"""Adaptador PostgreSQL para el CRUD administrativo del catálogo."""
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.errors import InventoryConflict, InventoryStorageUnavailable
from app.domain.inventory import InventoryPart, InventoryPartDraft

logger = logging.getLogger(__name__)

PART_COLUMNS = """
    id, code, name, category, description, unit_price, current_stock,
    minimum_threshold, active, created_at, updated_at
"""


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

    def create_part(self, part: InventoryPartDraft) -> InventoryPart:
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(
                    text("""INSERT INTO spare_parts
                            (code, name, category, description, unit_price, current_stock,
                             minimum_threshold, active)
                            VALUES (:code, :name, :category, :description, :unit_price,
                                    :current_stock, :minimum_threshold, TRUE)
                            RETURNING id, code, name, category, description, unit_price,
                                      current_stock, minimum_threshold, active, created_at, updated_at"""),
                    self._values(part),
                ).mappings().one()
            return self._part(row)
        except IntegrityError as exc:
            if self._is_code_unique_error(exc):
                raise InventoryConflict(
                    "Ya existe un repuesto con ese código.", code="duplicate", field="code"
                ) from exc
            raise self._storage_error(exc) from exc
        except SQLAlchemyError as exc:
            raise self._storage_error(exc) from exc

    def update_part(self, code: str, part: InventoryPartDraft) -> InventoryPart | None:
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(
                    text("""UPDATE spare_parts
                            SET name = :name, category = :category, description = :description,
                                unit_price = :unit_price, current_stock = :current_stock,
                                minimum_threshold = :minimum_threshold
                            WHERE code = :lookup_code AND active IS TRUE
                            RETURNING id, code, name, category, description, unit_price,
                                      current_stock, minimum_threshold, active, created_at, updated_at"""),
                    {**self._values(part), "lookup_code": code},
                ).mappings().first()
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
                row = session.execute(
                    text("DELETE FROM spare_parts WHERE code = :code RETURNING id"),
                    {"code": code},
                ).first()
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
