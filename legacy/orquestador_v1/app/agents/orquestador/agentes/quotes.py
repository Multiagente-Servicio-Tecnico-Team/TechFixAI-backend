from decimal import Decimal

from app.application.quotes import calculate_quote as calculate_shared_quote


def calculate_quote(
    labor_cost: Decimal,
    available_parts: list[dict[str, object]],
) -> tuple[Decimal, Decimal]:
    # Orchestrator quotes only validated in-stock catalog lines here.
    task_type = "sale" if Decimal(str(labor_cost)) == 0 else "maintenance"
    quote = calculate_shared_quote(
        labor_cost=labor_cost,
        labor_task_type=task_type,
        parts=available_parts,
    )
    return quote["parts_cost"], quote["total_amount"]
