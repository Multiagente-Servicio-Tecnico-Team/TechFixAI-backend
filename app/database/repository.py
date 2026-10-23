from __future__ import annotations

from decimal import Decimal
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import MetaData, Table, inspect, insert, select, update
from sqlalchemy.engine import Connection, Engine

from app.database.connection import get_engine


def _table(connection: Connection, name: str) -> Table:
    return Table(name, MetaData(), autoload_with=connection)


def _column(table: Table, *names: str):
    columns = {column.name.casefold(): column for column in table.columns}
    return next((columns[name.casefold()] for name in names if name.casefold() in columns), None)


def _insert_row(connection: Connection, table: Table, values: dict[str, object]) -> int:
    row = {
        column.name: value
        for key, value in values.items()
        if (column := _column(table, key)) is not None
    }
    missing = [
        column.name
        for column in table.columns
        if not column.primary_key
        and not column.nullable
        and column.default is None
        and column.server_default is None
        and column.identity is None
        and column.name not in row
        and column.autoincrement is not True
    ]
    if missing:
        raise RuntimeError(
            f"La tabla {table.name} requiere columnas no contempladas: {', '.join(missing)}"
        )

    primary_key = next(iter(table.primary_key.columns), None)
    if primary_key is None:
        raise RuntimeError(f"La tabla {table.name} no tiene clave primaria")
    return connection.execute(
        insert(table).values(**row).returning(primary_key)
    ).scalar_one()


def find_user_by_email(email: str, engine: Engine | None = None) -> dict[str, object] | None:
    engine = engine or get_engine()
    with engine.connect() as connection:
        table = _table(connection, "users")
        email_column = _column(table, "email")
        id_column = _column(table, "id")
        name_column = _column(table, "name")
        active_column = _column(table, "active", "activo")
        if email_column is None or id_column is None:
            raise RuntimeError("La tabla users debe tener columnas id y email")
        selected_columns = [id_column, email_column]
        if name_column is not None:
            selected_columns.append(name_column)
        conditions = [email_column.ilike(email.strip())]
        if active_column is not None:
            conditions.append(active_column.is_(True))
        row = connection.execute(
            select(*selected_columns).where(*conditions).limit(1)
        ).mappings().first()
        return dict(row) if row else None


def create_ticket(
    user_id: object,
    product: str,
    category: str,
    symptoms: str,
    engine: Engine | None = None,
) -> int:
    engine = engine or get_engine()
    with engine.begin() as connection:
        ticket = _table(connection, "tickets")
        return _insert_row(
            connection,
            ticket,
            {
                "code": f"TCK-{uuid4().hex[:12].upper()}",
                "codigo": f"TCK-{uuid4().hex[:12].upper()}",
                "customer_id": user_id,
                "cliente_id": user_id,
                "title": f"{product} - {category}"[:200],
                "failure_description": symptoms,
            },
        )


def update_ticket_intake(
    ticket_id: int,
    product: str,
    category: str,
    symptoms: str,
    engine: Engine | None = None,
) -> None:
    engine = engine or get_engine()
    with engine.begin() as connection:
        ticket = _table(connection, "tickets")
        id_column = _column(ticket, "id")
        title_column = _column(ticket, "title")
        description_column = _column(ticket, "failure_description")
        if id_column is None or title_column is None or description_column is None:
            raise RuntimeError("La tabla tickets no contiene las columnas de ingreso esperadas")
        connection.execute(
            update(ticket)
            .where(id_column == ticket_id)
            .values(
                {
                    title_column: f"{product} - {category}"[:200],
                    description_column: symptoms,
                }
            )
        )


def update_ticket_diagnosis(
    ticket_id: int,
    diagnosis: str,
    engine: Engine | None = None,
) -> None:
    engine = engine or get_engine()
    with engine.begin() as connection:
        ticket = _table(connection, "tickets")
        id_column = _column(ticket, "id")
        diagnosis_column = _column(ticket, "provisional_diagnosis")
        status_column = _column(ticket, "status", "estado")
        if id_column is None or diagnosis_column is None:
            raise RuntimeError("La tabla tickets no permite guardar el diagnóstico provisional")
        values = {diagnosis_column: diagnosis}
        if status_column is not None:
            values[status_column] = "IN_DIAGNOSIS"
        connection.execute(
            update(ticket)
            .where(id_column == ticket_id)
            .values(values)
        )


def _normalize(value: object) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", str(value).casefold())
        if unicodedata.category(character) != "Mn"
    )


def lookup_inventory(
    requested_name: str,
    quantity: int,
    engine: Engine | None = None,
) -> dict[str, object]:
    engine = engine or get_engine()
    tables = {name.casefold(): name for name in inspect(engine).get_table_names()}
    table_name = next(
        (tables[name] for name in ("spare_parts", "spare_part", "repuestos", "repuesto") if name in tables),
        None,
    )
    if table_name is None:
        raise RuntimeError("No se encontró la tabla de inventario spare_parts")

    with engine.connect() as connection:
        table = _table(connection, table_name)
        name_column = _column(table, "name", "nombre", "nombre_repuesto", "articulo", "producto")
        stock_column = _column(table,"current_stock","stock_actual","stock","cantidad","existencias","disponible")
        price_column = _column(table, "unit_price", "precio", "precio_unitario", "costo")
        id_column = _column(table, "id", "spare_part_id", "repuesto_id")
        code_column = _column(table, "code")
        category_column = _column(table, "category")
        description_column = _column(table, "description")
        active_column = _column(table, "active", "activo")
        if name_column is None or stock_column is None or price_column is None:
            raise RuntimeError(
                f"La tabla {table_name} debe incluir nombre, inventario y precio unitario"
            )
        query = select(table)
        if active_column is not None:
            query = query.where(active_column.is_(True))
        rows = connection.execute(query).mappings().all()

    requested = re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", _normalize(requested_name))
    requested_tokens = set(re.findall(r"[a-z0-9]+", requested))
    related = r"\b(?:para|compatibles?|compatibilidad|incluye|soporta|admite)\b"
    identity_relation = r"\bcon\b|" + related
    accessories = {"adaptador", "adaptadores", "adapter", "adapters", "carcasa", "carcasas",
                   "cable", "cables", "convertidor", "convertidores", "enclosure", "enclosures"}
    requested_accessories = accessories.intersection(re.findall(
        r"[a-z0-9]+", re.split(identity_relation, requested, maxsplit=1)[0]))

    def search_terms(value, include_related=False):
        normalized = re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", _normalize(value or ""))
        terms = set()
        for clause in re.split(r"[;,\n]|(?<=[.!?])\s+", normalized):
            clause = re.split(r"\b(?:no\s+(?:incluye|contiene|es)|sin)\b", clause, maxsplit=1)[0]
            if not include_related:
                clause = re.split(related, clause, maxsplit=1)[0]
            terms.update(re.findall(r"[a-z0-9]+", clause))
        return terms

    matches = []
    for candidate in rows:
        item_name = str(candidate[name_column.name])
        normalized_name = re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", _normalize(item_name))
        exact_code = code_column is not None and requested == _normalize(candidate[code_column.name])
        if exact_code or requested == normalized_name:
            matches.append((3 if exact_code else 2, candidate))
            continue
        item_accessories = accessories.intersection(re.findall(
            r"[a-z0-9]+", re.split(identity_relation, normalized_name, maxsplit=1)[0]))
        exact_category = category_column is not None and requested == _normalize(candidate[category_column.name])
        if requested_accessories != item_accessories and not exact_category:
            continue
        item_tokens = search_terms(item_name, include_related=True)
        for column in (category_column, description_column):
            if column is not None:
                item_tokens.update(search_terms(candidate[column.name], include_related=bool(item_accessories)))
        # Todos los términos deben coincidir: 5000GB no equivale a 500GB,
        # ni SATA a NVMe. La similitud parcial no confirma un producto.
        if requested_tokens and requested_tokens.issubset(item_tokens):
            matches.append((1, candidate))

    best = max((score for score, _ in matches), default=0)
    finalists = [row for score, row in matches if score == best]
    if len(finalists) != 1:
        result = {
            "requested_name": requested_name,
            "name": requested_name,
            "quantity": quantity,
            "stock": 0,
            "unit_price": Decimal("0.00"),
            "available": False,
            "inventory_id": None,
            "found": False,
            "match_status": "ambiguous" if finalists else "not_found",
        }
        if finalists and id_column is not None:
            result["candidates"] = [
                {"id": row[id_column.name], "name": str(row[name_column.name]),
                 "code": row[code_column.name] if code_column is not None else None,
                 "unit_price": str(Decimal(str(row[price_column.name] or 0))),
                 "current_stock": int(row[stock_column.name] or 0)}
                for row in finalists[:20]
            ]
        return result

    row = finalists[0]
    stock = int(row[stock_column.name] or 0)
    return {
        "requested_name": requested_name,
        "name": str(row[name_column.name]),
        "quantity": quantity,
        "stock": stock,
        "unit_price": Decimal(str(row[price_column.name] or 0)),
        "available": stock >= quantity,
        "inventory_id": row[id_column.name] if id_column is not None else None,
        "found": True,
    }


def save_quote(
    ticket_id: int,
    diagnosis: str,
    labor_cost: Decimal,
    available_parts: list[dict[str, object]],
    engine: Engine | None = None,
) -> tuple[int, Decimal]:
    engine = engine or get_engine()
    labor_cost = Decimal(str(labor_cost)).quantize(Decimal("0.01"))
    parts_total = sum(
        (
            Decimal(str(part["unit_price"])) * int(part["quantity"])
            for part in available_parts
        ),
        Decimal("0.00"),
    )
    parts_total = parts_total.quantize(Decimal("0.01"))
    total = labor_cost + parts_total
    with engine.begin() as connection:
        quotes = _table(connection, "quotes")
        quote_id = _insert_row(
            connection,
            quotes,
            {
                "ticket_id": ticket_id,
                "observations": diagnosis,
                "diagnostico": diagnosis,
                "labor_cost": labor_cost,
                "mano_obra": labor_cost,
                "parts_cost": parts_total,
                "total_amount": total,
                "total": total,
                "status": "PENDING",
                "estado": "Pendiente de aceptación",
            },
        )
        details = _table(connection, "quote_details")
        for part in available_parts:
            quantity = int(part["quantity"])
            unit_price = Decimal(str(part["unit_price"]))
            _insert_row(
                connection,
                details,
                {
                    "quote_id": quote_id,
                    "presupuesto_id": quote_id,
                    "spare_part_id": part["inventory_id"],
                    "repuesto_id": part.get("inventory_id"),
                    "name": part["name"],
                    "nombre": part["name"],
                    "quantity": quantity,
                    "cantidad": quantity,
                    "unit_price": unit_price,
                    "precio_unitario": unit_price,
                    "subtotal": unit_price * quantity,
                },
            )
        tickets = _table(connection, "tickets")
        ticket_key = _column(tickets, "id")
        ticket_status = _column(tickets, "status", "estado")
        if ticket_key is not None and ticket_status is not None:
            connection.execute(
                update(tickets)
                .where(ticket_key == ticket_id)
                .values({ticket_status: "QUOTED"})
            )
    return quote_id, total


def create_ticket_with_quote(
    user_id: object,
    product: str,
    category: str,
    symptoms: str,
    diagnosis: str,
    labor_cost: Decimal,
    available_parts: list[dict[str, object]],
    engine: Engine | None = None,
) -> tuple[int, int, Decimal]:
    engine = engine or get_engine()
    labor_cost = Decimal(str(labor_cost)).quantize(Decimal("0.01"))
    parts_total = sum(
        (
            Decimal(str(part["unit_price"])) * int(part["quantity"])
            for part in available_parts
        ),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    total = labor_cost + parts_total

    with engine.begin() as connection:
        tickets = _table(connection, "tickets")
        ticket_id = _insert_row(
            connection,
            tickets,
            {
                "code": f"TCK-{uuid4().hex[:12].upper()}",
                "customer_id": user_id,
                "title": f"{product} - {category}"[:200],
                "failure_description": symptoms,
                "provisional_diagnosis": diagnosis,
                "status": "IN_DIAGNOSIS",
            },
        )
        quotes = _table(connection, "quotes")
        quote_id = _insert_row(
            connection,
            quotes,
            {
                "ticket_id": ticket_id,
                "labor_cost": labor_cost,
                "parts_cost": parts_total,
                "total_amount": total,
                "status": "PENDING",
                "observations": diagnosis,
            },
        )
        details = _table(connection, "quote_details")
        for part in available_parts:
            quantity = int(part["quantity"])
            unit_price = Decimal(str(part["unit_price"]))
            _insert_row(
                connection,
                details,
                {
                    "quote_id": quote_id,
                    "spare_part_id": part["inventory_id"],
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "subtotal": unit_price * quantity,
                },
            )
        ticket_key = _column(tickets, "id")
        ticket_status = _column(tickets, "status")
        connection.execute(
            update(tickets)
            .where(ticket_key == ticket_id)
            .values({ticket_status: "QUOTED"})
        )

    return ticket_id, quote_id, total
from collections.abc import Callable
from decimal import Decimal
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


SessionFactory = Callable[[], Session]


class ServiceRepository:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        if session_factory is None:
            from app.database.connection import SessionLocal

            session_factory = SessionLocal
        self._session_factory = session_factory

    def find_customer(self, email: str) -> dict[str, Any] | None:
        query = text(
            """
            SELECT id, name, last_name
            FROM users
            WHERE LOWER(email) = LOWER(:email)
              AND active IS TRUE
              AND role::text = 'CUSTOMER'
            """
        )
        with self._session_factory() as session:
            customer = (
                session.execute(query, {"email": email.strip()})
                .mappings()
                .first()
            )
        return dict(customer) if customer else None

    def create_ticket(
        self,
        *,
        code: str,
        customer_id: int,
        title: str,
        failure_description: str,
        request_type: str,
        provisional_diagnosis: str,
    ) -> int:
        query = text(
            """
            INSERT INTO tickets (
                code,
                customer_id,
                title,
                failure_description,
                request_type,
                status,
                provisional_diagnosis
            )
            VALUES (
                :code,
                :customer_id,
                :title,
                :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                :provisional_diagnosis
            )
            RETURNING id
            """
        )
        with self._session_factory() as session, session.begin():
            ticket_id = session.execute(
                query,
                {
                    "code": code,
                    "customer_id": customer_id,
                    "title": title,
                    "failure_description": failure_description,
                    "request_type": request_type,
                    "provisional_diagnosis": provisional_diagnosis,
                },
            ).scalar_one()
        return int(ticket_id)

    def find_spare_parts(self, search_term: str) -> list[dict[str, Any]]:
        term = search_term.strip()
        normalized_name = re.sub(r"_+", " ", term).strip()
        escaped_name = (
            normalized_name.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )
        query = text(
            """
            SELECT id, code, name, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE
              AND (
                    LOWER(code) = LOWER(:term)
                    OR LOWER(name) = LOWER(:normalized_name)
                    OR name ILIKE :pattern ESCAPE '!'
              )
            ORDER BY
                CASE
                    WHEN LOWER(code) = LOWER(:term) THEN 0
                    WHEN LOWER(name) = LOWER(:normalized_name) THEN 1
                    ELSE 2
                END,
                name
            LIMIT 5
            """
        )
        with self._session_factory() as session:
            rows = session.execute(
                query,
                {
                    "term": term,
                    "normalized_name": normalized_name,
                    "pattern": f"%{escaped_name}%",
                },
            ).mappings()
            return [dict(row) for row in rows]

    def find_spare_part_alternatives(self, search_term: str) -> list[dict[str, Any]]:
        term = search_term.strip()
        category = re.split(r"[_\s-]+", term, maxsplit=1)[0].strip()
        escaped_category = (
            category.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )
        query = text(
            """
            SELECT id, code, name, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE
              AND (
                    code ILIKE :pattern ESCAPE '!'
                    OR name ILIKE :pattern ESCAPE '!'
              )
            ORDER BY
                CASE WHEN current_stock > 0 THEN 0 ELSE 1 END,
                name
            LIMIT 10
            """
        )
        with self._session_factory() as session:
            rows = session.execute(
                query,
                {"pattern": f"%{escaped_category}%"},
            ).mappings()
            return [dict(row) for row in rows]

    def create_ticket_with_quote(
        self,
        *,
        ticket_code: str,
        customer_id: int,
        title: str,
        failure_description: str,
        request_type: str,
        provisional_diagnosis: str,
        labor_cost: Decimal,
        parts_cost: Decimal,
        total_amount: Decimal,
        observations: str,
        parts: list[dict[str, Any]],
    ) -> tuple[int, int]:
        insert_ticket = text(
            """
            INSERT INTO tickets (
                code,
                customer_id,
                title,
                failure_description,
                request_type,
                status,
                provisional_diagnosis
            )
            VALUES (
                :code,
                :customer_id,
                :title,
                :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                :provisional_diagnosis
            )
            RETURNING id
            """
        )
        insert_quote = text(
            """
            INSERT INTO quotes (
                ticket_id,
                labor_cost,
                parts_cost,
                total_amount,
                status,
                observations
            )
            VALUES (
                :ticket_id,
                :labor_cost,
                :parts_cost,
                :total_amount,
                CAST('PENDING' AS quote_status_enum),
                :observations
            )
            RETURNING id
            """
        )
        update_ticket = text(
            """
            UPDATE tickets
            SET status = CAST('QUOTED' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id
            """
        )
        insert_detail = text(
            """
            INSERT INTO quote_details (
                quote_id,
                spare_part_id,
                quantity,
                unit_price,
                subtotal
            )
            VALUES (
                :quote_id,
                :spare_part_id,
                :quantity,
                :unit_price,
                :subtotal
            )
            """
        )
        with self._session_factory() as session, session.begin():
            ticket_id = session.execute(
                insert_ticket,
                {
                    "code": ticket_code,
                    "customer_id": customer_id,
                    "title": title,
                    "failure_description": failure_description,
                    "request_type": request_type,
                    "provisional_diagnosis": provisional_diagnosis,
                },
            ).scalar_one()
            quote_id = session.execute(
                insert_quote,
                {
                    "ticket_id": ticket_id,
                    "labor_cost": labor_cost,
                    "parts_cost": parts_cost,
                    "total_amount": total_amount,
                    "observations": observations,
                },
            ).scalar_one()
            updated = session.execute(update_ticket, {"ticket_id": ticket_id})
            if updated.rowcount != 1:
                raise LookupError(
                    f"No se pudo actualizar el ticket {ticket_id} a QUOTED."
                )
            for part in parts:
                session.execute(
                    insert_detail,
                    {
                        "quote_id": quote_id,
                        "spare_part_id": part["id"],
                        "quantity": part["quantity"],
                        "unit_price": part["unit_price"],
                        "subtotal": part["subtotal"],
                    },
                )
        return int(ticket_id), int(quote_id)

    def save_quote(
        self,
        *,
        ticket_id: int,
        labor_cost: Decimal,
        parts_cost: Decimal,
        total_amount: Decimal,
        observations: str,
        parts: list[dict[str, Any]],
    ) -> int:
        insert_quote = text(
            """
            INSERT INTO quotes (
                ticket_id,
                labor_cost,
                parts_cost,
                total_amount,
                status,
                observations
            )
            VALUES (
                :ticket_id,
                :labor_cost,
                :parts_cost,
                :total_amount,
                CAST('PENDING' AS quote_status_enum),
                :observations
            )
            RETURNING id
            """
        )
        update_ticket = text(
            """
            UPDATE tickets
            SET status = CAST('QUOTED' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id
            """
        )
        insert_detail = text(
            """
            INSERT INTO quote_details (
                quote_id,
                spare_part_id,
                quantity,
                unit_price,
                subtotal
            )
            VALUES (
                :quote_id,
                :spare_part_id,
                :quantity,
                :unit_price,
                :subtotal
            )
            """
        )

        with self._session_factory() as session, session.begin():
            updated = session.execute(
                update_ticket,
                {"ticket_id": ticket_id},
            )
            if updated.rowcount != 1:
                raise LookupError(
                    f"No se pudo actualizar el ticket {ticket_id} a QUOTED."
                )
            quote_id = session.execute(
                insert_quote,
                {
                    "ticket_id": ticket_id,
                    "labor_cost": labor_cost,
                    "parts_cost": parts_cost,
                    "total_amount": total_amount,
                    "observations": observations,
                },
            ).scalar_one()
            for part in parts:
                session.execute(
                    insert_detail,
                    {
                        "quote_id": quote_id,
                        "spare_part_id": part["id"],
                        "quantity": part["quantity"],
                        "unit_price": part["unit_price"],
                        "subtotal": part["subtotal"],
                    },
                )
        return int(quote_id)
