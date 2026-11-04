from decimal import Decimal
from typing import Any

from app.application.quotes import calculate_quote as calculate_shared_quote


def calculate_quote(
    *, labor_cost: Decimal, labor_task_type: str, parts: list[dict[str, Any]]
) -> dict[str, Any]:
    return calculate_shared_quote(
        labor_cost=labor_cost,
        labor_task_type=labor_task_type,
        parts=parts,
    )
