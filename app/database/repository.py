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

    def list_admin_tickets(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        request_type: str | None = None,
        origin: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        query = text(
            """
            SELECT t.id, t.code, COALESCE(t.commercial_customer_id, t.customer_id) AS customer_id, t.technician_id, t.origin, t.contact_name, t.contact_phone, t.contact_email,
                   t.advance_amount, t.advance_payment_method, t.title,
                   t.failure_description, t.request_type::text AS request_type,
                   t.diagnosis_type::text AS diagnosis_type,
                   t.status::text AS status, t.hardware_diagnosis,
                   t.software_diagnosis, t.estimated_labor_hours,
                   t.is_remote_service, t.created_at, t.updated_at,
                   COALESCE(c.display_name, u.name) AS customer_first_name, CASE WHEN c.id IS NULL THEN u.last_name ELSE NULL END AS customer_last_name,
                   COALESCE(t.contact_email,c.email,u.email) AS customer_email, COALESCE(t.contact_phone,c.phone,u.phone) AS customer_phone,
                   q.total_amount AS quote_total, q.status::text AS quote_status,
                   p.status::text AS payment_status,
                   p.payment_method::text AS payment_method, p.amount AS payment_amount
            FROM tickets t
            LEFT JOIN customers c ON c.id = t.commercial_customer_id
            LEFT JOIN users u ON u.id = t.customer_id
            LEFT JOIN LATERAL (
                SELECT id, total_amount, status
                FROM quotes WHERE ticket_id = t.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) q ON TRUE
            LEFT JOIN LATERAL (
                SELECT status, payment_method, amount
                FROM payments WHERE ticket_id = t.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) p ON TRUE
            WHERE (CAST(:status AS text) IS NULL OR t.status::text = CAST(:status AS text))
              AND (CAST(:request_type AS text) IS NULL OR t.request_type::text = CAST(:request_type AS text))
              AND (CAST(:origin AS text) IS NULL OR t.origin = CAST(:origin AS text))
              AND (
                CAST(:search AS text) IS NULL OR t.code ILIKE CAST(:search_pattern AS text)
                OR t.title ILIKE CAST(:search_pattern AS text)
                OR t.failure_description ILIKE CAST(:search_pattern AS text)
                OR COALESCE(t.contact_name, c.display_name, u.name) ILIKE CAST(:search_pattern AS text)
                OR COALESCE(u.last_name, '') ILIKE CAST(:search_pattern AS text)
                OR COALESCE(t.contact_email,u.email) ILIKE CAST(:search_pattern AS text)
                OR COALESCE(t.contact_phone,u.phone) ILIKE CAST(:search_pattern AS text)
              )
            ORDER BY t.created_at DESC NULLS LAST, t.id DESC
            LIMIT :limit OFFSET :offset
            """
        )
        params = {
            "status": status,
            "request_type": request_type,
            "origin": origin,
            "search": search,
            "search_pattern": f"%{search}%" if search else None,
            "limit": limit,
            "offset": offset,
        }
        count_query = text("""SELECT COUNT(*) FROM tickets t LEFT JOIN customers c ON c.id=t.commercial_customer_id LEFT JOIN users u ON u.id=t.customer_id
            WHERE (CAST(:status AS text) IS NULL OR t.status::text=CAST(:status AS text))
              AND (CAST(:request_type AS text) IS NULL OR t.request_type::text=CAST(:request_type AS text))
              AND (CAST(:origin AS text) IS NULL OR t.origin=CAST(:origin AS text))
              AND (CAST(:search AS text) IS NULL OR t.code ILIKE CAST(:search_pattern AS text) OR t.title ILIKE CAST(:search_pattern AS text)
                OR t.failure_description ILIKE CAST(:search_pattern AS text) OR COALESCE(t.contact_name,c.display_name,u.name) ILIKE CAST(:search_pattern AS text)
                OR COALESCE(u.last_name,'') ILIKE CAST(:search_pattern AS text) OR COALESCE(t.contact_email,u.email) ILIKE CAST(:search_pattern AS text)
                OR COALESCE(t.contact_phone,u.phone) ILIKE CAST(:search_pattern AS text))""")
        with self._session_factory() as session:
            count_params = {key: value for key, value in params.items() if key not in {"limit", "offset"}}
            total = int(session.execute(count_query, count_params).scalar_one())
            rows = [dict(row) for row in session.execute(query, params).mappings()]
            return {"items": rows, "total": total}

    def get_admin_ticket(self, ticket_id: int) -> dict[str, Any] | None:
        # Fetch by primary key with the same related quote/payment projection.
        query = text(
            """
            SELECT t.id, t.code, COALESCE(t.commercial_customer_id, t.customer_id) AS customer_id, t.technician_id, t.origin, t.contact_name, t.contact_phone, t.contact_email,
                   t.advance_amount, t.advance_payment_method, t.title,
                   t.failure_description, t.request_type::text AS request_type,
                   t.diagnosis_type::text AS diagnosis_type,
                   t.status::text AS status, t.hardware_diagnosis,
                   t.software_diagnosis, t.estimated_labor_hours,
                   t.is_remote_service, t.created_at, t.updated_at,
                   COALESCE(c.display_name, u.name) AS customer_first_name, CASE WHEN c.id IS NULL THEN u.last_name ELSE NULL END AS customer_last_name,
                   COALESCE(t.contact_email,c.email,u.email) AS customer_email, COALESCE(t.contact_phone,c.phone,u.phone) AS customer_phone,
                   q.id AS quote_id, q.quote_type::text AS quote_type, q.labor_cost AS quote_labor_cost,
                   q.parts_cost AS quote_parts_cost, q.total_amount AS quote_total, q.status::text AS quote_status,
                   q.observations AS quote_observations, q.created_at AS quote_created_at,
                   p.status::text AS payment_status,
                   p.payment_method::text AS payment_method, p.amount AS payment_amount
            FROM tickets t LEFT JOIN customers c ON c.id = t.commercial_customer_id LEFT JOIN users u ON u.id = t.customer_id
            LEFT JOIN LATERAL (
                SELECT id, quote_type, labor_cost, parts_cost, total_amount, status, observations, created_at FROM quotes WHERE ticket_id = t.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) q ON TRUE
            LEFT JOIN LATERAL (
                SELECT status, payment_method, amount FROM payments WHERE ticket_id = t.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) p ON TRUE
            WHERE t.id = :ticket_id
            """
        )
        with self._session_factory() as session:
            row = session.execute(query, {"ticket_id": ticket_id}).mappings().first()
        return dict(row) if row else None

    def find_active_customer_by_email(self, email: str) -> dict[str, Any] | None:
        query = text(
            """SELECT id, name, last_name, email, phone FROM users
               WHERE LOWER(email) = LOWER(:email) AND active IS TRUE
                 AND role::text = 'CUSTOMER' LIMIT 1"""
        )
        with self._session_factory() as session:
            row = session.execute(query, {"email": email.strip()}).mappings().first()
        return dict(row) if row else None

    def create_admin_ticket(self, *, values: dict[str, Any], code: str, actor_id: int | None = None) -> int:
        query = text(
            """INSERT INTO tickets (
                   code, commercial_customer_id, created_by_user_id, technician_id, title, failure_description, origin, contact_name, contact_phone, contact_email, advance_amount, advance_payment_method,
                   request_type, diagnosis_type, status, hardware_diagnosis,
                   software_diagnosis, estimated_labor_hours, is_remote_service
               ) VALUES (
                   :code, :commercial_customer_id, :actor_id, :technician_id, :title, :failure_description, :origin, :contact_name, :contact_phone, :contact_email, :advance_amount, :advance_payment_method,
                   CAST(:request_type AS request_type_enum),
                   CAST(:diagnosis_type AS diagnosis_type_enum),
                   CAST(:status AS ticket_status_enum), :hardware_diagnosis,
                   :software_diagnosis, :estimated_labor_hours, :is_remote_service
               ) RETURNING id"""
        )
        with self._session_factory() as session, session.begin():
            commercial_customer_id = values.get("customer_id")
            if commercial_customer_id is None:
                commercial_customer_id = session.execute(text("""INSERT INTO customers
                    (display_name, phone, email, origin, created_by_user_id)
                    VALUES (:name, :phone, :email, 'MANUAL', :actor) RETURNING id"""),
                    {"name": values["contact_name"], "phone": values["contact_phone"],
                     "email": values.get("contact_email"), "actor": actor_id}).scalar_one()
                session.execute(text("""INSERT INTO customer_audit_events
                    (customer_id, actor_user_id, event_type, changed_fields)
                    VALUES (:customer, :actor, 'CREATED', '{\"origin\":\"MANUAL\"}'::jsonb)"""),
                    {"customer": commercial_customer_id, "actor": actor_id})
            else:
                active = session.execute(text("SELECT id FROM customers WHERE id=:id AND active IS TRUE FOR UPDATE"),
                                         {"id": commercial_customer_id}).scalar_one_or_none()
                if active is None:
                    raise ValueError("El cliente comercial seleccionado no existe o está inactivo.")
            ticket_id = int(session.execute(query, {**values, "customer_id": None,
                                                     "commercial_customer_id": commercial_customer_id,
                                                     "actor_id": actor_id, "code": code}).scalar_one())
            if actor_id is not None:
                session.execute(text("INSERT INTO ticket_audit_events(ticket_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'CREATED',CAST(:fields AS jsonb))"), {"id": ticket_id, "actor": actor_id, "fields": '{"origin":"MANUAL"}'})
            return ticket_id

    def update_admin_ticket(self, ticket_id: int, values: dict[str, Any]) -> bool:
        if not values:
            return self.get_admin_ticket(ticket_id) is not None
        allowed = {
            "technician_id", "title", "failure_description", "request_type",
            "diagnosis_type", "status", "hardware_diagnosis",
            "software_diagnosis", "estimated_labor_hours", "is_remote_service", "contact_name", "contact_phone", "contact_email", "advance_amount", "advance_payment_method",
        }
        if set(values) - allowed:
            raise ValueError("El ticket contiene campos que no se pueden actualizar.")
        assignments = []
        params: dict[str, Any] = {"ticket_id": ticket_id}
        enum_columns = {"request_type": "request_type_enum", "diagnosis_type": "diagnosis_type_enum", "status": "ticket_status_enum"}
        for name, value in values.items():
            if name in enum_columns:
                assignments.append(f"{name} = CAST(:{name} AS {enum_columns[name]})")
            else:
                assignments.append(f"{name} = :{name}")
            params[name] = value
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        query = text(
            f"UPDATE tickets SET {', '.join(assignments)} WHERE id = :ticket_id RETURNING id"
        )
        with self._session_factory() as session, session.begin():
            result = session.execute(query, params).scalar_one_or_none()
        return result is not None

    def update_admin_ticket_audited(self, ticket_id: int, values: dict[str, Any], actor_id: int) -> bool:
        import json
        if not values:
            return self.get_admin_ticket(ticket_id) is not None
        allowed = {"technician_id", "title", "failure_description", "request_type", "diagnosis_type", "status", "hardware_diagnosis", "software_diagnosis", "estimated_labor_hours", "is_remote_service", "contact_name", "contact_phone", "contact_email", "advance_amount", "advance_payment_method"}
        if set(values) - allowed:
            raise ValueError("El ticket contiene campos no editables.")
        enum_columns = {"request_type": "request_type_enum", "diagnosis_type": "diagnosis_type_enum", "status": "ticket_status_enum"}
        assignments, params = [], {"ticket_id": ticket_id}
        for name, value in values.items():
            assignments.append(f"{name} = CAST(:{name} AS {enum_columns[name]})" if name in enum_columns else f"{name} = :{name}")
            params[name] = value
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        with self._session_factory() as session, session.begin():
            previous = session.execute(text("SELECT status::text FROM tickets WHERE id=:id FOR UPDATE"), {"id": ticket_id}).scalar_one_or_none()
            if previous is None:
                return False
            session.execute(text(f"UPDATE tickets SET {', '.join(assignments)} WHERE id=:ticket_id"), params)
            status_changed = "status" in values and values["status"] != previous
            event = "CANCELLED" if values.get("status") == "CANCELLED" else "STATUS_CHANGED" if status_changed else "UPDATED"
            fields = {key: (str(value) if value is not None else None) for key, value in values.items()}
            if status_changed:
                fields["status"] = {"from": previous, "to": values["status"]}
            session.execute(text("INSERT INTO ticket_audit_events(ticket_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,:event,CAST(:fields AS jsonb))"), {"id": ticket_id, "actor": actor_id, "event": event, "fields": json.dumps(fields)})
        return True

    def list_ticket_audit_events(self, ticket_id: int) -> list[dict[str, Any]]:
        query = text("SELECT event_type, actor_user_id, changed_fields, created_at FROM ticket_audit_events WHERE ticket_id=:id ORDER BY created_at,id")
        with self._session_factory() as session:
            return [dict(row) for row in session.execute(query, {"id": ticket_id}).mappings()]

    def create_admin_ticket_quote(self, *, ticket_id: int, actor_id: int, quote_type: str, labor_cost: Any, labor_task_type: str, parts: list[dict[str, int]], observations: str | None = None) -> dict[str, Any] | None:
        from decimal import Decimal
        with self._session_factory() as session, session.begin():
            ticket = session.execute(text("""SELECT t.request_type::text,t.status::text,t.commercial_customer_id,
                    COALESCE(t.contact_name,c.display_name) AS customer_name,
                    COALESCE(t.contact_phone,c.phone) AS customer_phone,
                    COALESCE(t.contact_email,c.email) AS customer_email
                FROM tickets t LEFT JOIN customers c ON c.id=t.commercial_customer_id
                WHERE t.id=:id FOR UPDATE OF t"""), {"id": ticket_id}).mappings().first()
            if ticket is None:
                return None
            if ticket["status"] == "CANCELLED":
                raise ValueError("No se puede cotizar un ticket cancelado.")
            if ticket["request_type"] not in {"REPAIR", "SUPPORT", "WARRANTY_CLAIM"} or quote_type != "REPAIR":
                raise ValueError("Solo los tickets de servicio admiten cotizaciones de servicio; las ventas se cotizan sin ticket.")
            if ticket["commercial_customer_id"] is None:
                raise ValueError("El ticket todavía no tiene cliente comercial migrado.")
            labor = Decimal(str(labor_cost)).quantize(Decimal("0.01"))
            parts_total = Decimal("0.00")
            lines = []
            for part in parts:
                row = session.execute(text("SELECT id,name,unit_price,current_stock,active FROM spare_parts WHERE id=:id FOR SHARE"), {"id": part["spare_part_id"]}).mappings().first()
                if row is None or not row["active"] or int(row["current_stock"]) < part["quantity"]:
                    raise ValueError("El repuesto no está disponible en la cantidad indicada.")
                price = Decimal(str(row["unit_price"]))
                subtotal = (price * part["quantity"]).quantize(Decimal("0.01"))
                parts_total += subtotal
                lines.append({"row": row, "quantity": part["quantity"], "price": price, "subtotal": subtotal})
            total = labor + parts_total
            quote_id = session.execute(text("""INSERT INTO quotes
                (ticket_id,customer_id,quote_type,labor_cost,parts_cost,total_amount,status,observations,
                 origin,created_by_user_id,customer_name_snapshot,customer_phone_snapshot,customer_email_snapshot)
                VALUES (:ticket,:customer,CAST(:type AS quote_type_enum),:labor,:parts,:total,'PENDING',:obs,
                        'MANUAL',:actor,:name,:phone,:email) RETURNING id"""), {
                "ticket": ticket_id, "customer": ticket["commercial_customer_id"],
                "type": quote_type, "labor": labor, "parts": parts_total, "total": total,
                "obs": observations, "actor": actor_id, "name": ticket["customer_name"],
                "phone": ticket["customer_phone"], "email": ticket["customer_email"],
            }).scalar_one()
            created_at = session.execute(text("SELECT created_at FROM quotes WHERE id=:id"), {"id": quote_id}).scalar_one()
            for line in lines:
                session.execute(text("INSERT INTO quote_details(quote_id,spare_part_id,custom_item_name,quantity,unit_price,subtotal) VALUES (:quote,:part,:name,:qty,:price,:subtotal)"), {"quote": quote_id, "part": line["row"]["id"], "name": line["row"]["name"], "qty": line["quantity"], "price": line["price"], "subtotal": line["subtotal"]})
            session.execute(text("INSERT INTO ticket_audit_events(ticket_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'QUOTE_CREATED',CAST(:fields AS jsonb))"), {"id": ticket_id, "actor": actor_id, "fields": '{"quote_id":' + str(quote_id) + ',"status":"PENDING"}'})
            session.execute(text("""INSERT INTO quote_audit_events(quote_id,actor_user_id,event_type,changed_fields)
                VALUES (:quote,:actor,'CREATED',CAST(:fields AS jsonb))"""), {
                "quote": quote_id, "actor": actor_id,
                "fields": '{"kind":"SERVICE","ticket_id":' + str(ticket_id) + ',"status":"PENDING"}',
            })
            return {"id": int(quote_id), "ticket_id": ticket_id, "quote_type": quote_type, "labor_task_type": labor_task_type, "labor_cost": labor, "parts_cost": parts_total, "total_amount": total, "status": "PENDING", "observations": observations, "created_at": created_at}

    def delete_admin_ticket(self, ticket_id: int) -> bool:
        return False
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
            SELECT t.id, t.commercial_customer_id AS customer_id, t.code, t.title, t.failure_description,
                   t.request_type::text AS request_type,
                   t.diagnosis_type::text AS diagnosis_type,
                   t.hardware_diagnosis, t.software_diagnosis,
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
            WHERE t.commercial_customer_id = :customer_id
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
        all_quotes_query = text("""SELECT q.ticket_id, q.id AS quote_id, q.status::text AS status,
                   q.labor_cost, q.parts_cost, q.total_amount, q.created_at
            FROM quotes q JOIN tickets t ON t.id=q.ticket_id
            WHERE t.commercial_customer_id=:customer_id
            ORDER BY q.ticket_id, q.created_at DESC NULLS LAST, q.id DESC""")
        with self._session_factory() as session:
            rows = session.execute(
                tickets_query, {"customer_id": customer_id}
            ).mappings().all()
            tickets = [dict(row) for row in rows]
            all_quotes = [dict(row) for row in session.execute(all_quotes_query, {"customer_id": customer_id}).mappings()]
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
        quote_lines = {}
        all_quote_ids = [int(item["quote_id"]) for item in all_quotes]
        if all_quote_ids:
            with self._session_factory() as session:
                for row in session.execute(details_query, {"quote_ids": all_quote_ids}).mappings():
                    item = dict(row)
                    quote_lines.setdefault(int(item.pop("quote_id")), []).append(item)
        quotes_by_ticket = {}
        for item in all_quotes:
            quote_id = int(item.pop("quote_id"))
            item["lines"] = quote_lines.get(quote_id, [])
            quotes_by_ticket.setdefault(int(item.pop("ticket_id")), []).append(item)
        for ticket in tickets:
            ticket["quotes"] = quotes_by_ticket.get(int(ticket["id"]), [])
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
        if request_type not in {"REPAIR", "SUPPORT", "PC_BUILD", "WARRANTY_CLAIM"}:
            raise ValueError("Tipo de ticket no admitido por el esquema.")
        query = text("""INSERT INTO tickets (code, commercial_customer_id, created_by_user_id,
            contact_name, contact_phone, contact_email, title, failure_description, request_type, status, origin)
            SELECT :code, c.id, c.user_id, c.display_name, c.phone, c.email, :title,
                :failure_description, CAST(:request_type AS request_type_enum),
                CAST('NEW' AS ticket_status_enum), 'ONLINE'
            FROM customers c WHERE c.id=:customer_id AND c.active IS TRUE AND c.user_id IS NOT NULL
            RETURNING id""")
        with self._session_factory() as session, session.begin():
            customer = session.execute(text("""SELECT c.id, c.user_id, c.display_name, c.phone, c.email,
                    u.active AS user_active, u.role::text AS user_role
                FROM public.customers c LEFT JOIN public.users u ON u.id=c.user_id
                WHERE c.id=:id AND c.active IS TRUE FOR UPDATE OF c"""),
                {"id": customer_id}).mappings().first()
            if (customer is None or customer["user_id"] is None or not customer["user_active"]
                    or customer["user_role"] != "CUSTOMER"):
                raise LookupError("El perfil del portal no está vinculado a una cuenta activa.")
            actor_user_id = int(customer["user_id"])
            existing = session.execute(text("""SELECT id, commercial_customer_id, title,
                    failure_description, request_type::text AS request_type
                FROM public.tickets WHERE code=:code FOR UPDATE"""), {"code": code}).mappings().first()
            if existing is not None:
                if (int(existing["commercial_customer_id"]) != int(customer_id)
                        or existing["title"] != title[:200]
                        or existing["failure_description"] != failure_description
                        or existing["request_type"] != request_type):
                    raise LookupError("El código del ticket ya pertenece a otra operación.")
                return int(existing["id"])
            ticket_id = session.execute(
                query,
                {
                    "code": code,
                    "customer_id": customer_id,
                    "title": title[:200],
                    "failure_description": failure_description,
                    "request_type": request_type,
                },
            ).scalar_one_or_none()
            if ticket_id is None:
                raise LookupError("No se pudo crear un ticket para el cliente autenticado.")
            session.execute(text("INSERT INTO ticket_audit_events(ticket_id,actor_user_id,event_type,changed_fields) VALUES (:id,:actor,'CREATED','{\"origin\":\"ONLINE\"}'::jsonb)"), {"id": ticket_id, "actor": actor_user_id})
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
                hardware_diagnosis = CASE
                    WHEN :diagnosis_type IN ('HARDWARE', 'HYBRID')
                    THEN :hardware_diagnosis ELSE hardware_diagnosis END,
                software_diagnosis = CASE
                    WHEN :diagnosis_type IN ('SOFTWARE', 'HYBRID')
                    THEN :software_diagnosis ELSE software_diagnosis END,
                status = CAST('IN_DIAGNOSIS' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id
              AND commercial_customer_id = :customer_id
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
        from app.domain.errors import StaleQuote
        from app.domain.money import to_money

        if quote_type != "REPAIR":
            raise ValueError("Los tickets solo admiten cotizaciones de servicio REPAIR.")
        labor_cost = to_money(labor_cost)
        parts_cost = to_money(parts_cost)
        total_amount = to_money(total_amount)
        if (labor_cost < 0 or parts_cost < 0 or total_amount <= 0
                or total_amount != labor_cost + parts_cost):
            raise ValueError("Los importes de la cotización no son consistentes.")
        if not payment_code or len(payment_code) > 100:
            raise ValueError("Se requiere una referencia de pago válida.")

        with self._session_factory() as session, session.begin():
            owner = session.execute(text("""
                SELECT t.id, t.commercial_customer_id, t.status::text AS ticket_status,
                       t.request_type::text AS request_type, t.customer_id AS legacy_user_id,
                       c.user_id, c.display_name, c.phone, c.email,
                       u.active AS user_active, u.role::text AS user_role
                FROM public.tickets t
                JOIN public.customers c ON c.id=t.commercial_customer_id
                JOIN public.users u ON u.id=c.user_id
                WHERE t.id=:ticket_id AND t.commercial_customer_id=:customer_id
                  AND t.request_type IN (CAST('REPAIR' AS request_type_enum), CAST('SUPPORT' AS request_type_enum))
                  AND c.active IS TRUE
                FOR UPDATE OF t, c
            """), {"ticket_id": ticket_id, "customer_id": customer_id}).mappings().first()
            if (owner is None or owner["user_active"] is not True
                    or owner["user_role"] != "CUSTOMER"):
                raise LookupError("El ticket no pertenece al cliente autenticado o no admite cotizaciones.")
            existing = session.execute(text("""
                SELECT q.id AS quote_id, p.id AS payment_id, p.payment_code,
                       p.status::text AS payment_status, q.total_amount
                FROM public.quotes q
                JOIN public.payments p ON p.quote_id=q.id
                WHERE q.ticket_id=:ticket_id AND q.customer_id=:customer_id
                  AND q.status::text='ACCEPTED' AND p.status::text='PENDING'
                ORDER BY q.id DESC LIMIT 1
            """), {"ticket_id": ticket_id, "customer_id": customer_id}).mappings().first()
            if existing:
                if to_money(existing["total_amount"]) != total_amount:
                    raise LookupError("El ticket ya tiene una cotización aceptada con pago pendiente.")
                return {
                    "quote_id": int(existing["quote_id"]),
                    "payment_id": int(existing["payment_id"]),
                    "payment_code": existing["payment_code"],
                    "payment_status": existing["payment_status"],
                }
            if owner["ticket_status"] not in {"NEW", "IN_DIAGNOSIS", "QUOTED"}:
                raise LookupError("El ticket ya no admite cotizaciones.")

            validated_parts = []
            sum_parts = Decimal("0.00")
            for part in parts:
                part_id = part.get("id", part.get("inventory_id", part.get("spare_part_id")))
                quantity = part.get("quantity")
                if type(part_id) is not int or part_id < 1 or type(quantity) is not int or quantity < 1:
                    raise ValueError("Cada repuesto requiere ID y cantidad positivos.")
                catalog = session.execute(text("""
                    SELECT id, unit_price, current_stock
                    FROM public.spare_parts
                    WHERE id=:id AND active IS TRUE
                    FOR UPDATE
                """), {"id": part_id}).mappings().first()
                if catalog is None or int(catalog["current_stock"]) < quantity:
                    raise StaleQuote()
                current_price = to_money(catalog["unit_price"])
                proposed_price = to_money(part["unit_price"])
                subtotal = to_money(proposed_price * quantity)
                if (current_price != proposed_price or to_money(part["subtotal"]) != subtotal):
                    raise StaleQuote()
                sum_parts += subtotal
                validated_parts.append({
                    "spare_part_id": part_id, "quantity": quantity,
                    "unit_price": current_price, "subtotal": subtotal,
                })
            if to_money(sum_parts) != parts_cost:
                raise ValueError("El subtotal de repuestos no coincide con sus líneas.")

            quote_id = session.execute(text("""
                INSERT INTO public.quotes (
                    ticket_id, quote_type, labor_cost, parts_cost, total_amount,
                    status, observations, customer_id, origin, created_by_user_id,
                    accepted_by_user_id, accepted_at, customer_name_snapshot,
                    customer_phone_snapshot, customer_email_snapshot
                ) VALUES (
                    :ticket_id, CAST('REPAIR' AS quote_type_enum), :labor_cost,
                    :parts_cost, :total_amount, CAST('ACCEPTED' AS quote_status_enum),
                    :observations, :customer_id, 'CHAT', :actor_user_id,
                    :actor_user_id, CURRENT_TIMESTAMP, :customer_name,
                    :customer_phone, :customer_email
                ) RETURNING id
            """), {
                "ticket_id": ticket_id, "labor_cost": labor_cost, "parts_cost": parts_cost,
                "total_amount": total_amount, "observations": observations,
                "customer_id": customer_id, "actor_user_id": int(owner["user_id"]),
                "customer_name": owner["display_name"], "customer_phone": owner["phone"],
                "customer_email": owner["email"],
            }).scalar_one()
            for part in validated_parts:
                session.execute(text("""
                    INSERT INTO public.quote_details (quote_id, spare_part_id, quantity, unit_price, subtotal)
                    VALUES (:quote_id, :spare_part_id, :quantity, :unit_price, :subtotal)
                """), {"quote_id": quote_id, **part})
            payment = session.execute(text("""
                INSERT INTO public.payments (
                    ticket_id, quote_id, customer_id, commercial_customer_id,
                    payment_code, amount, status
                ) VALUES (
                    :ticket_id, :quote_id, :user_id, :customer_id,
                    :payment_code, :amount, CAST('PENDING' AS payment_status_enum)
                ) RETURNING id, payment_code, status::text AS status
            """), {
                "ticket_id": ticket_id, "quote_id": quote_id,
                "user_id": int(owner["user_id"]), "customer_id": customer_id,
                "payment_code": payment_code, "amount": total_amount,
            }).mappings().one()
            updated = session.execute(text("""
                UPDATE public.tickets
                SET status=CAST('PAYMENT_PENDING' AS ticket_status_enum), updated_at=CURRENT_TIMESTAMP
                WHERE id=:ticket_id AND commercial_customer_id=:customer_id
                  AND status IN (CAST('NEW' AS ticket_status_enum), CAST('IN_DIAGNOSIS' AS ticket_status_enum), CAST('QUOTED' AS ticket_status_enum))
            """), {"ticket_id": ticket_id, "customer_id": customer_id})
            if updated.rowcount != 1:
                raise LookupError("No se pudo actualizar el ticket de servicio.")
            session.execute(text("""
                INSERT INTO public.quote_audit_events (quote_id, actor_user_id, event_type, changed_fields)
                VALUES (:quote_id, :actor, 'ACCEPTED', jsonb_build_object('origin','CHAT','payment_status','PENDING'))
            """), {"quote_id": quote_id, "actor": int(owner["user_id"])})
            session.execute(text("""
                INSERT INTO public.ticket_audit_events (ticket_id, actor_user_id, event_type, changed_fields)
                VALUES (:ticket_id, :actor, 'QUOTE_ACCEPTED', jsonb_build_object('quote_id',:quote_id,'payment_id',:payment_id))
            """), {"ticket_id": ticket_id, "actor": int(owner["user_id"]),
                   "quote_id": int(quote_id), "payment_id": int(payment["id"])})
        return {
            "quote_id": int(quote_id), "payment_id": int(payment["id"]),
            "payment_code": payment["payment_code"], "payment_status": payment["status"],
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
        """Create an online service ticket, accepted quote and pending payment atomically."""
        from app.domain.errors import StaleQuote
        from app.domain.money import to_money

        if type(customer_id) is not int or customer_id < 1:
            raise ValueError("Se requiere el cliente autenticado.")
        if quote_type != "REPAIR" or request_type not in {"REPAIR", "SUPPORT"}:
            raise ValueError("Los tickets solo admiten cotizaciones de reparación o soporte.")
        if diagnosis_type not in {"HARDWARE", "SOFTWARE", "HYBRID", "NONE"}:
            raise ValueError("Tipo de diagnóstico no admitido.")
        labor_cost, parts_cost, total_amount = map(to_money, (labor_cost, parts_cost, total_amount))
        if (total_amount <= 0 or labor_cost < 0 or parts_cost < 0
                or total_amount != labor_cost + parts_cost):
            raise ValueError("La cotización debe tener importes válidos.")
        if not payment_code or len(payment_code) > 100:
            raise ValueError("Se requiere una referencia de pago válida.")
        ticket_code = f"TCK-{uuid4().hex[:12].upper()}"
        with self._session_factory() as session, session.begin():
            owner = session.execute(text("""
                SELECT c.id, c.user_id, c.display_name, c.phone, c.email,
                       u.active AS user_active, u.role::text AS user_role
                FROM public.customers c
                JOIN public.users u ON u.id=c.user_id
                WHERE c.id=:customer_id AND c.active IS TRUE
                FOR UPDATE OF c
            """), {"customer_id": customer_id}).mappings().first()
            if (owner is None or owner["user_active"] is not True
                    or owner["user_role"] != "CUSTOMER"):
                raise LookupError("El perfil comercial no está vinculado a una cuenta cliente activa.")
            actor_user_id = int(owner["user_id"])
            ticket_id = session.execute(
                text("""
                    INSERT INTO public.tickets (
                        code, customer_id, commercial_customer_id, created_by_user_id,
                        contact_name, contact_phone, contact_email, title, failure_description,
                        request_type, diagnosis_type, status, hardware_diagnosis,
                        software_diagnosis, origin
                    ) VALUES (
                        :code, :user_id, :customer_id, :actor_user_id, :contact_name,
                        :contact_phone, :contact_email, :title, :failure_description,
                        CAST(:request_type AS request_type_enum), CAST(:diagnosis_type AS diagnosis_type_enum),
                        CAST('PAYMENT_PENDING' AS ticket_status_enum), :hardware_diagnosis,
                        :software_diagnosis, 'ONLINE'
                    ) RETURNING id
                """), {
                    "code": ticket_code, "user_id": actor_user_id,
                    "customer_id": customer_id, "actor_user_id": actor_user_id,
                    "contact_name": owner["display_name"], "contact_phone": owner["phone"],
                    "contact_email": owner["email"], "title": title[:200],
                    "failure_description": failure_description, "request_type": request_type,
                    "diagnosis_type": diagnosis_type,
                    "hardware_diagnosis": provisional_diagnosis if diagnosis_type in {"HARDWARE", "HYBRID"} else None,
                    "software_diagnosis": provisional_diagnosis if diagnosis_type in {"SOFTWARE", "HYBRID"} else None,
                }).scalar_one()
            validated_parts = []
            sum_parts = Decimal("0.00")
            for part in parts:
                part_id = part.get("id", part.get("inventory_id", part.get("spare_part_id")))
                quantity = part.get("quantity")
                if type(part_id) is not int or part_id < 1 or type(quantity) is not int or quantity < 1:
                    raise ValueError("Cada repuesto requiere ID y cantidad positivos.")
                catalog = session.execute(text("""
                    SELECT id, unit_price, current_stock FROM public.spare_parts
                    WHERE id=:id AND active IS TRUE FOR UPDATE
                """), {"id": part_id}).mappings().first()
                if catalog is None or int(catalog["current_stock"]) < quantity:
                    raise StaleQuote()
                current_price = to_money(catalog["unit_price"])
                proposed_price = to_money(part["unit_price"])
                subtotal = to_money(proposed_price * quantity)
                if current_price != proposed_price or to_money(part["subtotal"]) != subtotal:
                    raise StaleQuote()
                sum_parts += subtotal
                validated_parts.append({"spare_part_id": part_id, "quantity": quantity,
                                        "unit_price": current_price, "subtotal": subtotal})
            if to_money(sum_parts) != parts_cost:
                raise ValueError("El subtotal de repuestos no coincide con sus líneas.")
            quote_id = session.execute(text("""
                INSERT INTO public.quotes (
                    ticket_id, quote_type, labor_cost, parts_cost, total_amount, status,
                    observations, customer_id, origin, created_by_user_id, accepted_by_user_id,
                    accepted_at, customer_name_snapshot, customer_phone_snapshot, customer_email_snapshot
                ) VALUES (
                    :ticket_id, CAST('REPAIR' AS quote_type_enum), :labor_cost, :parts_cost,
                    :total_amount, CAST('ACCEPTED' AS quote_status_enum), :observations,
                    :customer_id, 'CHAT', :actor_user_id, :actor_user_id, CURRENT_TIMESTAMP,
                    :customer_name, :customer_phone, :customer_email
                ) RETURNING id
            """), {
                "ticket_id": ticket_id, "labor_cost": labor_cost, "parts_cost": parts_cost,
                "total_amount": total_amount, "observations": observations,
                "customer_id": customer_id, "actor_user_id": actor_user_id,
                "customer_name": owner["display_name"], "customer_phone": owner["phone"],
                "customer_email": owner["email"],
            }).scalar_one()
            for part in validated_parts:
                session.execute(
                    text("""INSERT INTO public.quote_details
                        (quote_id, spare_part_id, quantity, unit_price, subtotal)
                        VALUES (:quote_id, :spare_part_id, :quantity, :unit_price, :subtotal)"""),
                    {"quote_id": quote_id, **part},
                )
            payment = session.execute(text("""
                INSERT INTO public.payments (
                    ticket_id, quote_id, customer_id, commercial_customer_id,
                    payment_code, amount, status
                ) VALUES (
                    :ticket_id, :quote_id, :user_id, :customer_id, :payment_code,
                    :amount, CAST('PENDING' AS payment_status_enum)
                ) RETURNING id, payment_code, status::text AS status
            """), {
                "ticket_id": ticket_id, "quote_id": quote_id,
                "user_id": actor_user_id, "customer_id": customer_id,
                "payment_code": payment_code, "amount": total_amount,
            }).mappings().one()
            session.execute(text("""
                INSERT INTO public.ticket_audit_events (ticket_id, actor_user_id, event_type, changed_fields)
                VALUES (:ticket_id, :actor, 'CREATED', jsonb_build_object('origin','ONLINE','request_type',:request_type))
            """), {"ticket_id": ticket_id, "actor": actor_user_id, "request_type": request_type})
            session.execute(text("""
                INSERT INTO public.quote_audit_events (quote_id, actor_user_id, event_type, changed_fields)
                VALUES (:quote_id, :actor, 'ACCEPTED', jsonb_build_object('origin','CHAT','payment_status','PENDING'))
            """), {"quote_id": quote_id, "actor": actor_user_id})
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
            SELECT w.id, COALESCE(w.commercial_customer_id,c.id) AS customer_id, w.sales_order_id, w.warranty_code, w.item_or_service_name,
                   warranty_months, start_date, end_date, status::text AS status,
                   end_date >= CURRENT_DATE AS not_expired
            FROM warranties w
            LEFT JOIN customers c ON c.id=w.commercial_customer_id
                OR (w.commercial_customer_id IS NULL AND c.user_id=w.customer_id)
            WHERE w.warranty_code = :warranty_code
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
                SELECT 1 FROM warranties w LEFT JOIN customers c ON c.id=w.commercial_customer_id
                    OR (w.commercial_customer_id IS NULL AND c.user_id=w.customer_id)
                WHERE w.id = :warranty_id AND COALESCE(w.commercial_customer_id,c.id) = :customer_id
            )
            """
        )
        update_ticket = text(
            """
            UPDATE tickets
            SET status = CAST('WARRANTY_IN_REVIEW' AS ticket_status_enum),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :ticket_id AND commercial_customer_id = :customer_id
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
        ticket_id: int | None,
        customer_id: int,
        sales_order_id: int | None = None,
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
        if (ticket_id is None) == (sales_order_id is None):
            raise ValueError("Indica un ticket o una venta para la logística.")
        with self._session_factory() as session, session.begin():
            customer = session.execute(text("SELECT user_id FROM customers WHERE id=:id AND active IS TRUE"),
                {"id": customer_id}).mappings().first()
            if customer is None:
                raise LookupError("El cliente comercial no existe o está inactivo.")
            if ticket_id is not None:
                owned = session.execute(text("SELECT id FROM tickets WHERE id=:ticket AND commercial_customer_id=:customer"),
                    {"ticket": ticket_id, "customer": customer_id}).scalar_one_or_none()
            else:
                owned = session.execute(text("SELECT id FROM sales_orders WHERE id=:order AND customer_id=:customer"),
                    {"order": sales_order_id, "customer": customer_id}).scalar_one_or_none()
            if owned is None:
                raise LookupError("El caso de servicio o venta no pertenece al cliente.")
            existing = session.execute(
                text(
                    """
                    SELECT l.id, l.mode::text AS mode, l.status::text AS status,
                           l.courier_company, l.shipping_address
                    FROM logistics_records l
                    WHERE ((:ticket_id IS NOT NULL AND l.ticket_id = :ticket_id)
                        OR (:sales_order_id IS NOT NULL AND l.sales_order_id = :sales_order_id))
                      AND l.commercial_customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id, "sales_order_id": sales_order_id, "customer_id": customer_id},
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
                        ticket_id, sales_order_id, commercial_customer_id, created_by_user_id,
                        mode, status, courier_company, shipping_address
                    )
                    VALUES (:ticket_id,:sales_order_id,:customer_id,:actor_id,CAST(:mode AS logistics_mode_enum),
                           CAST('PENDING_RECEIPT' AS logistics_status_enum),
                           :courier_company,:shipping_address
                    RETURNING id
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "sales_order_id": sales_order_id,
                    "customer_id": customer_id,
                    "actor_id": customer["user_id"],
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
        ticket_id: int | None,
        quote_id: int,
        customer_id: int,
        warranty_code: str,
        item_or_service_name: str,
        sales_order_id: int | None = None,
        actor_user_id: int | None = None,
        warranty_months: int = 3,
        request_type: str = "PC_BUILD",
    ) -> dict[str, Any]:
        if warranty_months != 3:
            raise ValueError("La garantía del pedido debe tener una vigencia de 3 meses.")
        if request_type not in {"SALE", "PC_BUILD"}:
            raise ValueError("La garantía solo aplica a una venta o armado aceptado.")
        if (ticket_id is None) == (sales_order_id is None):
            raise ValueError("Indica un pedido pagado o un ticket de armado.")
        if request_type == "SALE" and sales_order_id is None:
            raise ValueError("La garantía de venta requiere un pedido pagado.")
        if request_type == "PC_BUILD" and ticket_id is not None:
            raise ValueError("La garantía de armado se vincula al pedido pagado, no a un ticket de servicio.")
        with self._session_factory() as session, session.begin():
            customer = session.execute(text("SELECT user_id FROM customers WHERE id=:id AND active IS TRUE"),
                {"id": customer_id}).mappings().first()
            if customer is None:
                raise LookupError("El cliente comercial no existe o está inactivo.")
            if sales_order_id is not None:
                quote = session.execute(text("""SELECT q.id,q.status::text AS status,o.status AS order_status
                    FROM quotes q JOIN sales_orders o ON o.quote_id=q.id JOIN payments p ON p.id=o.payment_id
                    WHERE q.id=:quote_id AND o.id=:order_id AND o.customer_id=:customer_id
                      AND q.customer_id=:customer_id AND q.quote_type=CAST(:quote_type AS quote_type_enum)
                      AND o.status='PAID' AND p.status='COMPLETED'
                    FOR UPDATE OF q,o"""), {
                    "quote_id": quote_id, "order_id": sales_order_id, "customer_id": customer_id,
                    "quote_type": "PC_BUILD" if request_type == "PC_BUILD" else "DIRECT_SALE",
                }).mappings().first()
                valid_order = quote is not None and quote["status"] == "ACCEPTED" and quote["order_status"] == "PAID"
            else:
                quote = session.execute(text("""SELECT q.id,q.status::text AS status
                    FROM quotes q JOIN tickets t ON t.id=q.ticket_id
                    WHERE q.id=:quote_id AND q.ticket_id=:ticket_id
                      AND q.customer_id=:customer_id AND t.commercial_customer_id=:customer_id
                      AND t.request_type=CAST(:request_type AS request_type_enum)
                    FOR UPDATE OF q"""), {
                    "quote_id": quote_id, "ticket_id": ticket_id,
                    "customer_id": customer_id, "request_type": request_type,
                }).mappings().first()
                valid_order = quote is not None and quote["status"] == "ACCEPTED"
            if not valid_order:
                raise LookupError(
                    "La garantía requiere una cotización aceptada de servicio o un pedido pagado del cliente."
                )
            existing = session.execute(
                text(
                    """
                    SELECT id, warranty_code
                    FROM warranties
                    WHERE ((:ticket_id IS NOT NULL AND ticket_id = :ticket_id)
                        OR (:sales_order_id IS NOT NULL AND sales_order_id = :sales_order_id))
                      AND quote_id = :quote_id AND commercial_customer_id = :customer_id
                    LIMIT 1
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "sales_order_id": sales_order_id,
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
                        ticket_id, sales_order_id, quote_id, customer_id, commercial_customer_id,
                        created_by_user_id, warranty_code,
                        item_or_service_name, warranty_months, start_date, end_date,
                        status, terms_and_conditions
                    )
                    VALUES (
                        :ticket_id, :sales_order_id, :quote_id, :legacy_customer_id, :customer_id,
                        :actor_id, :warranty_code,
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
                    "sales_order_id": sales_order_id,
                    "quote_id": quote_id,
                    "customer_id": customer_id,
                    "legacy_customer_id": customer["user_id"],
                    "actor_id": actor_user_id or customer["user_id"],
                    "warranty_code": warranty_code,
                    "item_or_service_name": item_or_service_name[:200],
                    "terms_and_conditions": (
                        "Garantía de 3 meses asociada a los productos o servicio "
                        "incluidos en la cotización aceptada o pedido pagado."
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
                    SELECT p.id, p.ticket_id, p.amount, p.status::text AS status,
                           c.user_id AS requested_by_user_id
                    FROM payments p
                    LEFT JOIN customers c ON c.id=p.commercial_customer_id
                    WHERE p.id = :payment_id AND p.commercial_customer_id = :customer_id
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
                    INSERT INTO refunds (payment_id, ticket_id, amount, reason, status, requested_by_user_id)
                    VALUES (:payment_id, :ticket_id, :amount, :reason,
                            CAST('REQUESTED' AS refund_status_enum), :requested_by_user_id)
                    RETURNING id, payment_id, ticket_id, amount, status::text AS status
                    """
                ),
                {
                    "payment_id": payment_id,
                    "ticket_id": payment["ticket_id"],
                    "amount": amount,
                    "reason": reason,
                    "requested_by_user_id": payment.get("requested_by_user_id"),
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
                    WHERE payment_code = :payment_code AND commercial_customer_id = :customer_id
                    """
                ),
                {"payment_code": payment_code, "customer_id": customer_id},
            ).mappings().first()
        return int(row["id"]) if row else None
