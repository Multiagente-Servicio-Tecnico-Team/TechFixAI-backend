import unittest
from decimal import Decimal

from app.agents.orquestador.agentes.quotes import calculate_quote


class CalculateQuoteTests(unittest.TestCase):
    def test_totals_include_only_parts_passed_to_calculator(self):
        parts = [
            {"unit_price": "125.50", "quantity": 2},
            {"unit_price": "0.10", "quantity": 1},
        ]

        parts_total, total = calculate_quote(Decimal("300"), parts)

        self.assertEqual(parts_total, Decimal("251.10"))
        self.assertEqual(total, Decimal("551.10"))

    def test_quote_without_parts_contains_only_labor(self):
        parts_total, total = calculate_quote(Decimal("300.25"), [])

        self.assertEqual(parts_total, Decimal("0.00"))
        self.assertEqual(total, Decimal("300.25"))

    def test_labor_is_rounded_to_currency_precision(self):
        parts_total, total = calculate_quote(Decimal("10.005"), [])

        self.assertEqual(parts_total, Decimal("0.00"))
        self.assertEqual(total, Decimal("10.01"))


if __name__ == "__main__":
    unittest.main()