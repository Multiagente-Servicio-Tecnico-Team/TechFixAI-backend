from __future__ import annotations

from decimal import Decimal
import re
import unicodedata
from uuid import uuid4

from sqlalchemy import MetaData, Table, bindparam, inspect, insert, select, update
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
                "diagnosis_type": "NONE",
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
        diagnosis_column = _column(
            ticket, "hardware_diagnosis", "provisional_diagnosis"
        )
        status_column = _column(ticket, "status", "estado")
        if id_column is None or diagnosis_column is None:
            raise RuntimeError("La tabla tickets no permite guardar el diagnóstico")
        values = {diagnosis_column: diagnosis}
        diagnosis_type_column = _column(ticket, "diagnosis_type")
        if diagnosis_type_column is not None:
            values[diagnosis_type_column] = "HARDWARE"
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


def _catalog_tokens(value: object) -> list[str]:
    """Normalize catalog text while keeping specs such as 32GB and 3200MHz atomic."""
    normalized = _normalize(value)
    normalized = re.sub(r"\bddr\s*([345])\b", r"ddr\1", normalized)
    normalized = re.sub(r"(?<=\d)\s*(?:gigabytes?|gigas?|gb)\b", "gb", normalized)
    normalized = re.sub(r"(?<=\d)\s*(?:terabytes?|tb)\b", "tb", normalized)
    normalized = re.sub(r"(?<=\d)\s*(?:mhz|mt\s*/\s*s)\b", "mtps", normalized)
    normalized = re.sub(
        r"(?<=\d)\s+(?=(?:gb|tb|mhz|ghz|w|mm|cm|inch|pulgadas)\b)",
        "",
        normalized,
    )
    return re.findall(r"[a-z]*\d+(?:\.\d+)?[a-z]*|[a-z]+", normalized)


_CATALOG_CATEGORY_PREFIXES = {
    "ram": ("ram",),
    "storage": ("almacenamiento",),
    "cpu": ("procesador",),
    "gpu": ("tarjeta de video",),
    "motherboard": ("placa madre",),
    "power_supply": ("fuente de poder",),
    "battery": ("bateria laptop",),
    "screen": ("pantalla laptop",),
    "charger": ("cargador",),
    "monitor": ("monitores",),
    "case": ("gabinete",),
    "cooling": ("refrigeracion pc",),
    "keyboard": ("teclado laptop",),
    "peripheral": ("perifericos",),
    "maintenance": ("mantenimiento",),
    "supplies": ("insumos",),
    "adapter": ("adaptador",),
    "cable": ("cable",),
    "tool": ("herramientas",),
    "expansion": ("tarjeta de expansion",),
    "laptop_part": ("repuesto laptop",),
    "energy": ("energia",),
}


_CATALOG_QUERY_ALIASES = {
    "ram": ("ram", "memoria", "memorias"),
    "storage": ("ssd", "disco", "discos", "almacenamiento", "nvme", "sata"),
    "cpu": ("cpu", "procesador", "procesadores"),
    "gpu": ("gpu", "video", "grafica", "graficas", "tarjeta de video", "tarjeta grafica"),
    "motherboard": ("placa madre", "motherboard", "placa base"),
    "power_supply": ("fuente", "fuentes", "psu", "fuente de poder"),
    "battery": ("bateria", "baterias"),
    "screen": ("pantalla", "pantallas"),
    "charger": ("cargador", "cargadores"),
    "monitor": ("monitor", "monitores"),
    "case": ("gabinete", "case"),
    "cooling": ("refrigeracion", "disipador", "ventilador", "cooler"),
    "keyboard": ("teclado", "teclados"),
    "peripheral": ("periferico", "perifericos", "mouse", "raton", "audifono"),
    "maintenance": ("mantenimiento",),
    "supplies": ("insumo", "insumos"),
    "adapter": ("adaptador", "adaptadores"),
    "cable": ("cable", "cables"),
    "tool": ("herramienta", "herramientas"),
    "expansion": ("expansion",),
    "laptop_part": ("repuesto", "repuestos"),
    "energy": ("energia",),
}


_CATALOG_STOPWORDS = {
    "a", "al", "alguna", "algunas", "algun", "algunos", "articulo",
    "articulos", "busco", "catalogo", "con", "cuanto", "cuantos",
    "cuantas", "de", "del", "dime", "disponible", "disponibles",
    "disponibilidad", "el", "en", "hay", "la", "las", "lo", "los",
    "me", "modelo", "modelos", "necesito", "opcion", "opciones", "para",
    "por", "precio", "precios", "quiero", "quisiera", "stock", "tienen",
    "tiene", "un", "una", "unas", "unos", "venden", "vende", "ver",
    "comprar", "compra", "favor", "producto", "productos", "que", "marca",
    "marcas", "capacidad", "capacidades", "generacion", "generaciones",
    "formato", "interfaz", "velocidad", "tipo", "prefiero", "preferencia",
    "pulgada", "pulgadas",
}

_CATALOG_FAMILY_WORDS = {
    "ram": {"ram", "memoria", "memorias"},
    "storage": {"ssd", "disco", "discos", "almacenamiento"},
    "cpu": {"cpu", "procesador", "procesadores"},
    "gpu": {"gpu", "video", "grafica", "graficas", "tarjeta"},
    "motherboard": {"placa", "madre", "motherboard", "base"},
    "power_supply": {"fuente", "fuentes", "psu", "poder"},
    "battery": {"bateria", "baterias"},
    "screen": {"pantalla", "pantallas"},
    "charger": {"cargador", "cargadores"},
    "monitor": {"monitor", "monitores"},
    "case": {"gabinete", "case"},
    "cooling": {"refrigeracion", "disipador", "ventilador", "cooler"},
    "keyboard": {"teclado", "teclados"},
    "peripheral": {"periferico", "perifericos"},
    "maintenance": {"mantenimiento"},
    "supplies": {"insumo", "insumos"},
    "adapter": {"adaptador", "adaptadores"},
    "cable": {"cable", "cables"},
    "tool": {"herramienta", "herramientas"},
    "expansion": {"expansion"},
    "laptop_part": {"repuesto", "repuestos"},
    "energy": {"energia"},
}


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
        code_column = _column(table, "code", "sku", "codigo", "código")
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
    matches = []
    for candidate in rows:
        item_name = str(candidate[name_column.name])
        normalized_name = re.sub(r"(\d)\s+(gb|tb)\b", r"\1\2", _normalize(item_name))
        item_tokens = set(re.findall(r"[a-z0-9]+", normalized_name))
        # Todos los términos deben coincidir: 5000GB no equivale a 500GB,
        # ni SATA a NVMe. La similitud parcial no confirma un producto.
        score = 2 if requested == normalized_name else 1
        if requested_tokens and requested_tokens.issubset(item_tokens):
            matches.append((score, candidate))

    best = max((score for score, _ in matches), default=0)
    finalists = [row for score, row in matches if score == best]
    if len(finalists) != 1:
        return {
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

    row = finalists[0]
    stock = int(row[stock_column.name] or 0)
    return {
        "requested_name": requested_name,
        "name": str(row[name_column.name]),
        "quantity": quantity,
        "stock": stock,
        "current_stock": stock,
        "unit_price": Decimal(str(row[price_column.name] or 0)),
        "available": stock >= quantity,
        "inventory_id": row[id_column.name] if id_column is not None else None,
        "code": row[code_column.name] if code_column is not None else None,
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

    def lookup_inventory(
        self, requested_name: str, quantity: int
    ) -> dict[str, object]:
        """Read current stock and price through this repository's engine."""
        with self._session_factory() as session:
            engine = session.get_bind()
            return lookup_inventory(
                requested_name=requested_name,
                quantity=quantity,
                engine=engine,
            )

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

    def list_customer_tickets(self, customer_id: int) -> list[dict[str, Any]]:
        """Return only this customer's tickets with their latest quote details."""
        tickets_query = text(
            """
            SELECT t.id, t.code, t.title, t.failure_description,
                   t.request_type::text AS request_type,
                   t.status::text AS status, t.created_at, t.updated_at,
                   q.id AS quote_id, q.status::text AS quote_status,
                   q.labor_cost, q.parts_cost, q.total_amount,
                   q.created_at AS quote_created_at
            FROM tickets t
            LEFT JOIN LATERAL (
                SELECT id, status, labor_cost, parts_cost, total_amount, created_at
                FROM quotes
                WHERE ticket_id = t.id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            ) q ON TRUE
            WHERE t.customer_id = :customer_id
            ORDER BY t.created_at DESC NULLS LAST, t.id DESC
            """
        )
        details_query = text(
            """
            SELECT qd.quote_id, COALESCE(sp.name, qd.custom_item_name, 'Artículo') AS name,
                   qd.quantity, qd.unit_price, qd.subtotal
            FROM quote_details qd
            LEFT JOIN spare_parts sp ON sp.id = qd.spare_part_id
            WHERE qd.quote_id IN :quote_ids
            ORDER BY qd.id
            """
        ).bindparams(bindparam("quote_ids", expanding=True))
        with self._session_factory() as session:
            rows = session.execute(
                tickets_query, {"customer_id": customer_id}
            ).mappings().all()
            tickets = [dict(row) for row in rows]
            quote_ids = [ticket["quote_id"] for ticket in tickets if ticket["quote_id"]]
            details: dict[int, list[dict[str, Any]]] = {}
            if quote_ids:
                for row in session.execute(
                    details_query, {"quote_ids": quote_ids}
                ).mappings():
                    item = dict(row)
                    details.setdefault(int(item.pop("quote_id")), []).append(item)

        for ticket in tickets:
            quote_id = ticket.pop("quote_id")
            ticket["quote"] = (
                {
                    "status": ticket.pop("quote_status"),
                    "labor_cost": ticket.pop("labor_cost"),
                    "parts_cost": ticket.pop("parts_cost"),
                    "total_amount": ticket.pop("total_amount"),
                    "created_at": ticket.pop("quote_created_at"),
                    "lines": details.get(int(quote_id), []),
                }
                if quote_id
                else None
            )
            if not quote_id:
                for field in (
                    "quote_status", "labor_cost", "parts_cost",
                    "total_amount", "quote_created_at",
                ):
                    ticket.pop(field, None)
        return tickets

    def create_intake_ticket(
        self,
        *,
        code: str,
        customer_id: int,
        title: str,
        failure_description: str,
        request_type: str,
    ) -> int:
        if request_type not in {"REPAIR", "SUPPORT", "SALE", "PC_BUILD", "WARRANTY_CLAIM"}:
            raise ValueError("Tipo de ticket no admitido por el esquema.")
        query = text(
            """
            INSERT INTO tickets (
                code, customer_id, title, failure_description, request_type, status
            )
            VALUES (
                :code, :customer_id, :title, :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST('NEW' AS ticket_status_enum)
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
                    "title": title[:200],
                    "failure_description": failure_description,
                    "request_type": request_type,
                },
            ).scalar_one()
        return int(ticket_id)

    def update_ticket_diagnosis(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        diagnosis: str,
        diagnosis_type: str,
    ) -> None:
        if diagnosis_type not in {"HARDWARE", "SOFTWARE", "HYBRID"}:
            raise ValueError("Tipo de diagnóstico no admitido.")
        query = text(
            """
            UPDATE tickets
            SET diagnosis_type = CAST(:diagnosis_type AS diagnosis_type_enum),
                hardware_diagnosis = :hardware_diagnosis,
                software_diagnosis = :software_diagnosis,
                status = CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id
              AND customer_id = :customer_id
              AND request_type IN (
                  CAST('REPAIR' AS request_type_enum),
                  CAST('SUPPORT' AS request_type_enum)
              )
              AND status IN (
                  CAST('NEW' AS ticket_status_enum),
                  CAST('IN_DIAGNOSIS' AS ticket_status_enum)
              )
            RETURNING id
            """
        )
        with self._session_factory() as session, session.begin():
            updated_ticket = session.execute(
                query,
                {
                    "ticket_id": ticket_id,
                    "customer_id": customer_id,
                    "diagnosis_type": diagnosis_type,
                    "hardware_diagnosis": (
                        diagnosis if diagnosis_type in {"HARDWARE", "HYBRID"} else None
                    ),
                    "software_diagnosis": (
                        diagnosis if diagnosis_type in {"SOFTWARE", "HYBRID"} else None
                    ),
                },
            ).scalar_one_or_none()
            if updated_ticket is None:
                raise LookupError("No se pudo guardar el diagnóstico en el ticket.")

    def accept_ticket_quote(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        quote_type: str,
        labor_cost: Decimal,
        parts_cost: Decimal,
        total_amount: Decimal,
        observations: str,
        parts: list[dict[str, Any]],
        payment_code: str,
    ) -> dict[str, Any]:
        if quote_type not in {"REPAIR", "DIRECT_SALE", "PC_BUILD"}:
            raise ValueError("Tipo de cotización no admitido.")
        if total_amount <= 0 or (quote_type != "REPAIR" and not parts):
            raise ValueError("La cotización requiere un importe positivo y artículos.")
        insert_quote = text(
            """
            INSERT INTO quotes (
                ticket_id, quote_type, labor_cost, parts_cost, total_amount,
                status, observations
            )
            VALUES (
                :ticket_id, CAST(:quote_type AS quote_type_enum), :labor_cost,
                :parts_cost, :total_amount, CAST('ACCEPTED' AS quote_status_enum),
                :observations
            )
            RETURNING id
            """
        )
        insert_detail = text(
            """
            INSERT INTO quote_details (
                quote_id, spare_part_id, quantity, unit_price, subtotal
            )
            VALUES (:quote_id, :spare_part_id, :quantity, :unit_price, :subtotal)
            """
        )
        insert_payment = text(
            """
            INSERT INTO payments (
                ticket_id, quote_id, customer_id, payment_code, amount, status
            )
            VALUES (
                :ticket_id, :quote_id, :customer_id, :payment_code, :amount,
                CAST('PENDING' AS payment_status_enum)
            )
            RETURNING id, payment_code, amount, status
            """
        )
        update_ticket = text(
            """
            UPDATE tickets
            SET status = CAST('PAYMENT_PENDING' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id AND customer_id = :customer_id
            """
        )
        with self._session_factory() as session, session.begin():
            existing = session.execute(
                text(
                    """
                    SELECT q.id AS quote_id, p.id AS payment_id,
                           p.payment_code, p.status AS payment_status
                    FROM quotes q
                    JOIN payments p ON p.quote_id = q.id
                    JOIN tickets t ON t.id = q.ticket_id
                    WHERE q.ticket_id = :ticket_id
                      AND t.customer_id = :customer_id
                      AND q.status::text = 'ACCEPTED'
                    ORDER BY q.id DESC
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id, "customer_id": customer_id},
            ).mappings().first()
            if existing:
                return dict(existing)

            quote_id = session.execute(
                insert_quote,
                {
                    "ticket_id": ticket_id,
                    "quote_type": quote_type,
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
            payment = session.execute(
                insert_payment,
                {
                    "ticket_id": ticket_id,
                    "quote_id": quote_id,
                    "customer_id": customer_id,
                    "payment_code": payment_code,
                    "amount": total_amount,
                },
            ).mappings().one()
            updated = session.execute(
                update_ticket,
                {"ticket_id": ticket_id, "customer_id": customer_id},
            )
            if updated.rowcount != 1:
                raise LookupError("No se pudo actualizar el ticket comercial.")
        return {
            "quote_id": int(quote_id),
            "payment_id": int(payment["id"]),
            "payment_code": payment["payment_code"],
            "payment_status": payment["status"],
        }

    def cancel_ticket(self, ticket_id: int, customer_id: int) -> None:
        query = text(
            """
            UPDATE tickets
            SET status = CAST('CANCELLED' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id AND customer_id = :customer_id
            """
        )
        with self._session_factory() as session, session.begin():
            result = session.execute(
                query, {"ticket_id": ticket_id, "customer_id": customer_id}
            )
            if result.rowcount != 1:
                raise LookupError("No se pudo cancelar el ticket.")

    def create_accepted_ticket_quote(
        self,
        *,
        customer_id: int,
        request_type: str,
        quote_type: str,
        title: str,
        failure_description: str,
        provisional_diagnosis: str,
        diagnosis_type: str,
        labor_cost: Decimal,
        parts_cost: Decimal,
        total_amount: Decimal,
        observations: str,
        parts: list[dict[str, Any]],
        payment_code: str,
    ) -> dict[str, Any]:
        """Atomically create an accepted ticket quote and pending payment."""
        if type(customer_id) is not int or customer_id < 1:
            raise ValueError("Se requiere el cliente autenticado.")
        expected_request = {
            "REPAIR": "REPAIR",
            "DIRECT_SALE": "SALE",
            "PC_BUILD": "PC_BUILD",
        }
        if expected_request.get(quote_type) != request_type:
            raise ValueError("El tipo de ticket no corresponde a la cotización.")
        if diagnosis_type not in {"HARDWARE", "SOFTWARE", "HYBRID", "NONE"}:
            raise ValueError("Tipo de diagnóstico no admitido.")
        if total_amount <= 0 or labor_cost < 0 or parts_cost < 0:
            raise ValueError("La cotización debe tener importes válidos.")
        ticket_code = f"TCK-{uuid4().hex[:12].upper()}"
        insert_ticket = text(
            """
            INSERT INTO tickets (
                code, customer_id, title, failure_description, request_type,
                diagnosis_type, status, hardware_diagnosis, software_diagnosis
            )
            VALUES (
                :code, :customer_id, :title, :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST(:diagnosis_type AS diagnosis_type_enum),
                CAST('PAYMENT_PENDING' AS ticket_status_enum),
                :hardware_diagnosis, :software_diagnosis
            )
            RETURNING id
            """
        )
        insert_quote = text(
            """
            INSERT INTO quotes (
                ticket_id, quote_type, labor_cost, parts_cost, total_amount,
                status, observations
            )
            VALUES (
                :ticket_id, CAST(:quote_type AS quote_type_enum), :labor_cost,
                :parts_cost, :total_amount, CAST('ACCEPTED' AS quote_status_enum),
                :observations
            )
            RETURNING id
            """
        )
        insert_detail = text(
            """
            INSERT INTO quote_details (
                quote_id, spare_part_id, quantity, unit_price, subtotal
            )
            VALUES (:quote_id, :spare_part_id, :quantity, :unit_price, :subtotal)
            """
        )
        insert_payment = text(
            """
            INSERT INTO payments (
                ticket_id, quote_id, customer_id, payment_code, amount, status
            )
            VALUES (
                :ticket_id, :quote_id, :customer_id, :payment_code, :amount,
                CAST('PENDING' AS payment_status_enum)
            )
            RETURNING id, payment_code, status
            """
        )
        with self._session_factory() as session, session.begin():
            ticket_id = session.execute(
                insert_ticket,
                {
                    "code": ticket_code,
                    "customer_id": customer_id,
                    "title": title[:200],
                    "failure_description": failure_description,
                    "request_type": request_type,
                    "diagnosis_type": diagnosis_type,
                    "hardware_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"HARDWARE", "HYBRID"}
                        else None
                    ),
                    "software_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"SOFTWARE", "HYBRID"}
                        else None
                    ),
                },
            ).scalar_one()
            quote_id = session.execute(
                insert_quote,
                {
                    "ticket_id": ticket_id,
                    "quote_type": quote_type,
                    "labor_cost": labor_cost,
                    "parts_cost": parts_cost,
                    "total_amount": total_amount,
                    "observations": observations,
                },
            ).scalar_one()
            for part in parts:
                if type(part.get("quantity")) is not int or part["quantity"] < 1:
                    raise ValueError("Cantidad de artículo no válida.")
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
            payment = session.execute(
                insert_payment,
                {
                    "ticket_id": ticket_id,
                    "quote_id": quote_id,
                    "customer_id": customer_id,
                    "payment_code": payment_code,
                    "amount": total_amount,
                },
            ).mappings().one()
        return {
            "ticket_id": int(ticket_id),
            "ticket_code": ticket_code,
            "quote_id": int(quote_id),
            "payment_id": int(payment["id"]),
            "payment_code": payment["payment_code"],
            "payment_status": payment["status"],
            "total_amount": total_amount,
        }

    def find_warranty(self, warranty_code: str) -> dict[str, Any] | None:
        query = text(
            """
            SELECT id, customer_id, warranty_code, item_or_service_name,
                   warranty_months, start_date, end_date, status::text AS status,
                   end_date >= CURRENT_DATE AS not_expired
            FROM warranties
            WHERE warranty_code = :warranty_code
            LIMIT 1
            """
        )
        with self._session_factory() as session:
            row = session.execute(
                query, {"warranty_code": warranty_code.strip()}
            ).mappings().first()
        return dict(row) if row else None

    def create_warranty_claim(
        self,
        *,
        warranty_id: int,
        ticket_id: int,
        customer_id: int,
        claim_code: str,
        reason: str,
    ) -> None:
        query = text(
            """
            INSERT INTO warranty_claims (warranty_id, ticket_id, claim_code, reason, status)
            SELECT :warranty_id, :ticket_id, :claim_code, :reason,
                   CAST('IN_REVIEW' AS warranty_claim_status_enum)
            WHERE EXISTS (
                SELECT 1 FROM warranties
                WHERE id = :warranty_id AND customer_id = :customer_id
            )
            """
        )
        update_ticket = text(
            """
            UPDATE tickets
            SET status = CAST('WARRANTY_IN_REVIEW' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id AND customer_id = :customer_id
            """
        )
        with self._session_factory() as session, session.begin():
            inserted = session.execute(
                query,
                {
                    "warranty_id": warranty_id,
                    "ticket_id": ticket_id,
                    "customer_id": customer_id,
                    "claim_code": claim_code,
                    "reason": reason,
                },
            )
            if inserted.rowcount != 1:
                raise LookupError("La póliza no corresponde al cliente.")
            updated = session.execute(
                update_ticket,
                {"ticket_id": ticket_id, "customer_id": customer_id},
            )
            if updated.rowcount != 1:
                raise LookupError("No se pudo actualizar el ticket de garantía.")

    def create_logistics_record(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        mode: str,
        courier_company: str | None = None,
        shipping_address: str | None = None,
    ) -> int:
        if mode not in {"PHYSICAL_STORE", "COURIER_SHIPMENT"}:
            raise ValueError("Modalidad logística no admitida.")
        if mode == "COURIER_SHIPMENT" and not (
            courier_company and shipping_address
        ):
            raise ValueError("Courier requiere empresa y dirección.")
        with self._session_factory() as session, session.begin():
            existing = session.execute(
                text(
                    """
                    SELECT l.id, l.mode::text AS mode, l.status::text AS status,
                           l.courier_company, l.shipping_address
                    FROM logistics_records l
                    JOIN tickets t ON t.id = l.ticket_id
                    WHERE l.ticket_id = :ticket_id AND t.customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id, "customer_id": customer_id},
            ).mappings().first()
            if existing is not None:
                same_preference = (
                    existing["mode"] == mode
                    and existing["courier_company"] == courier_company
                    and existing["shipping_address"] == shipping_address
                )
                if same_preference:
                    return int(existing["id"])
                if existing["status"] != "PENDING_RECEIPT":
                    raise ValueError(
                        "La modalidad logística no puede cambiar después de la recepción."
                    )
                updated_id = session.execute(
                    text(
                        """
                        UPDATE logistics_records
                        SET mode = CAST(:mode AS logistics_mode_enum),
                            courier_company = :courier_company,
                            shipping_address = :shipping_address,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :record_id
                        RETURNING id
                        """
                    ),
                    {
                        "record_id": existing["id"],
                        "mode": mode,
                        "courier_company": courier_company,
                        "shipping_address": shipping_address,
                    },
                ).scalar_one_or_none()
                if updated_id is None:
                    raise LookupError("No se pudo actualizar la modalidad logística.")
                return int(updated_id)
            record_id = session.execute(
                text(
                    """
                    INSERT INTO logistics_records (
                        ticket_id, mode, status, courier_company, shipping_address
                    )
                    SELECT :ticket_id, CAST(:mode AS logistics_mode_enum),
                           CAST('PENDING_RECEIPT' AS logistics_status_enum),
                           :courier_company, :shipping_address
                    WHERE EXISTS (
                        SELECT 1 FROM tickets
                        WHERE id = :ticket_id AND customer_id = :customer_id
                    )
                    RETURNING id
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "customer_id": customer_id,
                    "mode": mode,
                    "courier_company": courier_company,
                    "shipping_address": shipping_address,
                },
            ).scalar_one_or_none()
            if record_id is None:
                raise LookupError("No se pudo registrar la modalidad logística.")
        return int(record_id)

    def create_order_warranty(
        self,
        *,
        ticket_id: int,
        quote_id: int,
        customer_id: int,
        warranty_code: str,
        item_or_service_name: str,
        warranty_months: int = 3,
        request_type: str = "PC_BUILD",
    ) -> dict[str, Any]:
        if warranty_months != 3:
            raise ValueError("La garantía del pedido debe tener una vigencia de 3 meses.")
        if request_type not in {"SALE", "PC_BUILD"}:
            raise ValueError("La garantía solo aplica a una venta o armado aceptado.")
        with self._session_factory() as session, session.begin():
            quote = session.execute(
                text(
                    """
                    SELECT q.id, q.status::text AS status
                    FROM quotes q
                    JOIN tickets t ON t.id = q.ticket_id
                    WHERE q.id = :quote_id
                      AND q.ticket_id = :ticket_id
                      AND t.customer_id = :customer_id
                      AND t.request_type = CAST(:request_type AS request_type_enum)
                    FOR UPDATE OF q
                    """
                ),
                {
                    "quote_id": quote_id,
                    "ticket_id": ticket_id,
                    "customer_id": customer_id,
                    "request_type": request_type,
                },
            ).mappings().first()
            if quote is None or quote["status"] != "ACCEPTED":
                raise LookupError(
                    "La garantía requiere una cotización aceptada "
                    "del cliente autenticado."
                )
            existing = session.execute(
                text(
                    """
                    SELECT id, warranty_code
                    FROM warranties
                    WHERE ticket_id = :ticket_id AND quote_id = :quote_id
                      AND customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "quote_id": quote_id,
                    "customer_id": customer_id,
                },
            ).mappings().first()
            if existing is not None:
                return dict(existing)
            created = session.execute(
                text(
                    """
                    INSERT INTO warranties (
                        ticket_id, quote_id, customer_id, warranty_code,
                        item_or_service_name, warranty_months, start_date, end_date,
                        status, terms_and_conditions
                    )
                    VALUES (
                        :ticket_id, :quote_id, :customer_id, :warranty_code,
                        :item_or_service_name, 3, CURRENT_DATE,
                        (CURRENT_DATE + make_interval(months => 3))::date,
                        CAST('ACTIVE' AS warranty_status_enum),
                        :terms_and_conditions
                    )
                    RETURNING id, warranty_code
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "quote_id": quote_id,
                    "customer_id": customer_id,
                    "warranty_code": warranty_code,
                    "item_or_service_name": item_or_service_name[:200],
                    "terms_and_conditions": (
                        "Garantía de 3 meses asociada a los productos o servicio "
                        "incluidos en la cotización aceptada. El pedido sigue "
                        "pendiente de pago y logística; este registro no confirma "
                        "reserva, recepción, ensamble ni entrega."
                    ),
                },
            ).mappings().one()
            return dict(created)

    def create_ticket(
        self,
        *,
        code: str,
        customer_id: int,
        title: str,
        failure_description: str,
        request_type: str,
        provisional_diagnosis: str,
        diagnosis_type: str = "HARDWARE",
    ) -> int:
        if diagnosis_type not in {"HARDWARE", "SOFTWARE", "HYBRID", "NONE"}:
            raise ValueError("Tipo de diagnóstico no admitido por el esquema.")
        query = text(
            """
            INSERT INTO tickets (
                code,
                customer_id,
                title,
                failure_description,
                request_type,
                diagnosis_type,
                status,
                hardware_diagnosis,
                software_diagnosis
            )
            VALUES (
                :code,
                :customer_id,
                :title,
                :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST(:diagnosis_type AS diagnosis_type_enum),
                CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                :hardware_diagnosis,
                :software_diagnosis
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
                    "diagnosis_type": diagnosis_type,
                    "hardware_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"HARDWARE", "HYBRID"}
                        else None
                    ),
                    "software_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"SOFTWARE", "HYBRID"}
                        else None
                    ),
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
            SELECT id, code, name, category, description, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE
              AND (
                    LOWER(code) = LOWER(:term)
                    OR LOWER(name) = LOWER(:normalized_name)
                    OR name ILIKE :pattern ESCAPE '!'
                    OR COALESCE(category, '') ILIKE :pattern ESCAPE '!'
                    OR COALESCE(description, '') ILIKE :pattern ESCAPE '!'
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

    def find_catalog_items(self, search_term: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500:
            raise ValueError("El límite de búsqueda debe estar entre 1 y 40.")
        term = search_term.strip()
        if not term:
            return []

        query_tokens = _catalog_tokens(term)
        normalized_term = _normalize(term)
        family = next(
            (
                key
                for key, aliases in _CATALOG_QUERY_ALIASES.items()
                if any(re.search(rf"\b{re.escape(alias)}\b", normalized_term) for alias in aliases)
            ),
            None,
        )
        categories = _CATALOG_CATEGORY_PREFIXES.get(family, ())
        ignored_tokens = set(_CATALOG_STOPWORDS)
        if family:
            ignored_tokens.update(_CATALOG_FAMILY_WORDS[family])

        # Form factor is a real filter for memory, not merely another text term.
        if family == "ram":
            if any(token in query_tokens for token in ("laptop", "notebook", "sodimm")):
                categories = ("ram laptop",)
            elif any(token in query_tokens for token in ("desktop", "udimm", "escritorio", "sobremesa")):
                categories = ("ram desktop",)
            ignored_tokens.update({"laptop", "notebook", "sodimm", "desktop", "udimm", "escritorio", "sobremesa"})

        # Normalize equivalent unit spellings and keep numeric specs atomic.
        tokens = list(dict.fromkeys(token for token in query_tokens if token not in ignored_tokens))
        if not categories and not tokens:
            return []

        # Exact normalized tokens avoid substring errors such as 32 GB matching
        # 3200 MHz, while category aliases let "memoria RAM" find RAM-only names.
        query = text(
            """
            SELECT id, code, name, category, description, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE
              AND current_stock > 0
              AND unit_price > 0
            """
        )
        with self._session_factory() as session:
            rows = [dict(row) for row in session.execute(query).mappings()]

        matches = []
        for item in rows:
            category_tokens = _catalog_tokens(item.get("category", ""))
            category_text = " ".join(category_tokens)
            if categories and not any(category_text.startswith(prefix) for prefix in categories):
                continue
            searchable = set(
                _catalog_tokens(
                    " ".join(
                        str(item.get(field) or "")
                        for field in ("code", "name", "category", "description")
                    )
                )
            )
            if all(token in searchable for token in tokens):
                matches.append(item)

        matches.sort(key=lambda item: (-int(item["current_stock"]), str(item["name"]).casefold()))
        return matches[:limit]

    def find_spare_part_by_code(self, code: str) -> dict[str, Any] | None:
        query = text(
            """
            SELECT id, code, name, category, description, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE AND LOWER(code) = LOWER(:code)
            """
        )
        with self._session_factory() as session:
            row = session.execute(query, {"code": code.strip()}).mappings().first()
        return dict(row) if row else None

    def find_spare_part_alternatives(self, search_term: str) -> list[dict[str, Any]]:
        term = search_term.strip()
        category = re.split(r"[_\s-]+", term, maxsplit=1)[0].strip()
        escaped_category = (
            category.replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_")
        )
        family_filters = {
            "RAM": """
                AND (
                    code ILIKE 'RAM%'
                    OR category ILIKE 'RAM%'
                    OR name ILIKE 'RAM %'
                    OR name ILIKE 'Memoria RAM%'
                )
            """,
            "SSD": """
                AND (
                    code ILIKE 'SSD%'
                    OR (
                        category ILIKE '%Almacenamiento%'
                        AND name ILIKE '%SSD%'
                    )
                )
            """,
            "FUENTE": """
                AND (
                    code ILIKE 'PSU%'
                    OR category ILIKE '%Fuente de Poder%'
                    OR name ILIKE 'Fuente%'
                )
            """,
            "PASTA": """
                AND (
                    code ILIKE 'PASTE%'
                    OR code ILIKE '%THERM%'
                    OR (
                        category ILIKE '%Insumos%'
                        AND (
                            name ILIKE '%térmica%'
                            OR name ILIKE '%thermal%'
                        )
                    )
                )
            """,
            "VENTILADOR": """
                AND (
                    code ILIKE 'FAN%'
                    OR code ILIKE 'COOL%'
                    OR name ILIKE 'Ventilador%'
                )
            """,
            "REP": """
                AND (
                    code ILIKE 'REP-BAT%'
                    OR category ILIKE '%Batería Laptop%'
                    OR (
                        name ILIKE '%batería%'
                        AND name NOT ILIKE '%RTC%'
                        AND name NOT ILIKE '%CMOS%'
                    )
                )
            """,
            "PILA": """
                AND (
                    code ILIKE '%CR2032%'
                    OR name ILIKE '%CR2032%'
                )
            """,
            "SERVICIO": """
                AND (
                    category ILIKE '%Mantenimiento%'
                    OR name ILIKE 'Servicio%'
                )
            """,
        }
        family_filter = family_filters.get(category.upper(), "")
        query = text(
            f"""
            SELECT id, code, name, category, unit_price, current_stock
            FROM spare_parts
            WHERE active IS TRUE
              AND (
                    code ILIKE :pattern ESCAPE '!'
                    OR name ILIKE :pattern ESCAPE '!'
                    OR category ILIKE :pattern ESCAPE '!'
              )
              {family_filter}
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
        diagnosis_type: str = "HARDWARE",
    ) -> tuple[int, int]:
        if diagnosis_type not in {"HARDWARE", "SOFTWARE", "HYBRID", "NONE"}:
            raise ValueError("Tipo de diagnóstico no admitido por el esquema.")
        insert_ticket = text(
            """
            INSERT INTO tickets (
                code,
                customer_id,
                title,
                failure_description,
                request_type,
                diagnosis_type,
                status,
                hardware_diagnosis,
                software_diagnosis
            )
            VALUES (
                :code,
                :customer_id,
                :title,
                :failure_description,
                CAST(:request_type AS request_type_enum),
                CAST(:diagnosis_type AS diagnosis_type_enum),
                CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                :hardware_diagnosis,
                :software_diagnosis
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
                    "diagnosis_type": diagnosis_type,
                    "hardware_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"HARDWARE", "HYBRID"}
                        else None
                    ),
                    "software_diagnosis": (
                        provisional_diagnosis
                        if diagnosis_type in {"SOFTWARE", "HYBRID"}
                        else None
                    ),
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

    def request_refund(
        self,
        *,
        customer_id: int,
        payment_id: int,
        amount: Decimal,
        reason: str,
    ) -> dict[str, Any]:
        """Register a pending refund request after a locked eligibility check.

        This operation never updates a payment status or calls a payment provider.
        """
        with self._session_factory() as session, session.begin():
            payment = session.execute(
                text(
                    """
                    SELECT id, ticket_id, amount, status::text AS status
                    FROM payments
                    WHERE id = :payment_id AND customer_id = :customer_id
                    FOR UPDATE
                    """
                ),
                {"payment_id": payment_id, "customer_id": customer_id},
            ).mappings().first()
            if payment is None:
                raise ValueError("No se encontró un pago completado de este cliente.")
            if payment["status"] != "COMPLETED":
                raise ValueError("Solo se puede solicitar el reembolso de un pago completado.")

            unresolved = session.execute(
                text(
                    """
                    SELECT 1 FROM refunds
                    WHERE payment_id = :payment_id
                      AND status::text IN ('REQUESTED', 'APPROVED')
                    LIMIT 1
                    """
                ),
                {"payment_id": payment_id},
            ).first()
            if unresolved:
                raise ValueError("Ya existe una solicitud de reembolso pendiente para este pago.")

            processed = session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(amount), 0)
                    FROM refunds
                    WHERE payment_id = :payment_id AND status::text = 'PROCESSED'
                    """
                ),
                {"payment_id": payment_id},
            ).scalar_one()
            remaining = Decimal(str(payment["amount"])) - Decimal(str(processed or 0))
            if amount > remaining:
                raise ValueError("El importe supera el saldo aún reembolsable.")

            inserted = session.execute(
                text(
                    """
                    INSERT INTO refunds (payment_id, ticket_id, amount, reason, status)
                    VALUES (:payment_id, :ticket_id, :amount, :reason,
                            CAST('REQUESTED' AS refund_status_enum))
                    RETURNING id, payment_id, ticket_id, amount, status::text AS status
                    """
                ),
                {
                    "payment_id": payment_id,
                    "ticket_id": payment["ticket_id"],
                    "amount": amount,
                    "reason": reason,
                },
            ).mappings().one()
        return dict(inserted)

    def find_payment_id_by_code(self, customer_id: int, payment_code: str) -> int | None:
        """Resolve a customer-owned payment reference without exposing other accounts."""
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT id FROM payments
                    WHERE payment_code = :payment_code AND customer_id = :customer_id
                    """
                ),
                {"payment_code": payment_code, "customer_id": customer_id},
            ).mappings().first()
        return int(row["id"]) if row else None
