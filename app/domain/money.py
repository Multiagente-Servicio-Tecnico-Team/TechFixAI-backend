"""Importes con Decimal y dos decimales; el dinero nunca se representa con float."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
CURRENCY = "PEN"


def to_money(value: object) -> Decimal:
    """Convierte un importe (Decimal, int, str o float) a Decimal con dos decimales."""
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def money_text(value: object) -> str:
    """Importe como texto con dos decimales, el formato del contrato JSON."""
    return f"{to_money(value):.2f}"
