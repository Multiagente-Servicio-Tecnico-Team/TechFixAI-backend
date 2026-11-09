"""Pure key adapters; completeness and business rules remain with their consumers.

Callers select the schema explicitly. These functions neither parse messages nor
authorize operations, and never change public tool arguments or stored values.
"""
from copy import deepcopy
from typing import Any


class DataCompatibilityError(ValueError):
    """Legacy and canonical keys contain contradictory values."""


def _same_value(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return len(left) == len(right) and all(
            any(_same_value(key, other_key) and _same_value(value, other_value)
                for other_key, other_value in right.items())
            for key, value in left.items()
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _same_value(a, b) for a, b in zip(left, right)
        )
    return left == right


def _normalize(data: dict[str, Any], aliases: dict[str, str]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TypeError("Expected a dictionary")
    if any(not isinstance(key, str) for key in data):
        raise TypeError("Expected string keys")
    for legacy, canonical in aliases.items():
        if legacy in data and canonical in data:
            if not _same_value(data[legacy], data[canonical]):
                raise DataCompatibilityError(
                    f"Conflicting keys: {legacy}, {canonical}"
                )
    result = deepcopy(data)
    for legacy, canonical in aliases.items():
        if legacy in result:
            if canonical not in result:
                result[canonical] = result[legacy]
            del result[legacy]
    return result


def normalize_handoff_history_entry(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize history endpoints without adding record-only fields."""
    return _normalize(data, {"origen": "origin", "destino": "destination"})


def normalize_handoff_record(data: dict[str, Any]) -> dict[str, Any]:
    """Preserve revisions, progress tokens and additional audit metadata."""
    return _normalize(data, {
        "origen": "origin", "destino": "destination", "motivo": "reason",
    })


def normalize_handoff_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize structured handoff data; tool names and scope values stay intact."""
    return _normalize(data, {
        "accion": "action", "motivo": "reason", "alcance": "scope",
        "nombre_repuesto": "part_name", "cantidad": "quantity",
        "consulta": "query",
    })


def normalize_sales_inventory_item(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize the intermediate inventory projection produced by Sales."""
    return _normalize(data, {
        "encontrado": "found", "nombre": "name", "cantidad": "quantity",
        "precio_unitario": "unit_price", "disponible": "available",
    })


def normalize_inventory_result(data: dict[str, Any]) -> dict[str, Any]:
    """Copy the already-English raw inventory schema without inventing aliases."""
    return _normalize(data, {})
