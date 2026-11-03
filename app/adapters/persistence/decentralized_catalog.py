"""Catalog boundary for the original decentralized matching semantics only."""
import re
from decimal import Decimal
from sqlalchemy import inspect, MetaData, Table, select
from sqlalchemy.engine import Engine
from app.database.connection import get_engine
from app.database.repository import _column, _normalize, _table

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
