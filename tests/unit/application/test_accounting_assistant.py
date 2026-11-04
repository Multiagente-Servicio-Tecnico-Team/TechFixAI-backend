"""Pruebas aisladas de la guía contable, sin repositorio ni servicios externos."""
import unittest

from app.application.accounting_assistant import prepare_manual_entry
from app.application.accounting_assistant import AccountingAssistant
from app.domain.accounting import AccountingValidationError


def manual_data():
    return {
        "operation_date": "2026-11-03", "concept": "Ingreso manual", "detail": "Datos de ADMIN",
        "category_id": 1,
        "lines": [
            {"account_code": "A", "account_name": "Cuenta A", "debit": "12.50", "credit": "0.00"},
            {"account_code": "B", "account_name": "Cuenta B", "debit": "0.00", "credit": "12.50"},
        ],
    }


class AccountingAssistantTests(unittest.TestCase):
    def test_valid_manual_payload_returns_only_temporary_data(self):
        result = prepare_manual_entry(manual_data())
        self.assertEqual(result["debit_total"], "12.50")
        self.assertEqual(result["credit_total"], "12.50")
        self.assertEqual(result["currency"], "PEN")
        self.assertNotIn("id", result)
        self.assertNotIn("status", result)

    def test_missing_data_is_not_inferred(self):
        data = manual_data()
        del data["category_id"]
        with self.assertRaisesRegex(AccountingValidationError, "category_id"):
            prepare_manual_entry(data)

    def test_unbalanced_entry_is_rejected(self):
        data = manual_data()
        data["lines"][1]["credit"] = "11.00"
        with self.assertRaisesRegex(AccountingValidationError, "balance"):
            prepare_manual_entry(data)

    def test_both_sides_positive_is_rejected(self):
        data = manual_data()
        data["lines"][0]["credit"] = "1.00"
        with self.assertRaisesRegex(AccountingValidationError, "exactamente"):
            prepare_manual_entry(data)


class FakeService:
    def __init__(self):
        self.writes = []
        self.filters = None
        self.entry_status = "CONFIRMED"

    def list_categories(self):
        return [{"id": 1, "code": "OTHER", "name": "Otro"}]

    def list_entries(self, **filters):
        self.filters = filters
        return {"items": [], "total": 0, "limit": filters["limit"], "offset": filters["offset"]}

    def get_entry(self, entry_id):
        return {"id": entry_id, "status": self.entry_status, "reversal_of_entry_id": None,
                "operation_date": "2026-11-03", "concept": "Manual", "detail": "Detalle",
                "debit_total": "10.00", "credit_total": "10.00", "currency": "PEN", "lines": []}

    def create_entry(self, **kwargs):
        self.writes.append(("create", kwargs))

    def reverse_entry(self, **kwargs):
        self.writes.append(("reverse", kwargs))


class AccountingAssistantQueriesTests(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()

    def test_only_authenticated_admin_can_construct_assistant(self):
        for role in ("CUSTOMER", "TECHNICIAN", "ADMIN_FROM_PAYLOAD", None):
            with self.subTest(role=role), self.assertRaises(PermissionError):
                AccountingAssistant(self.service, authenticated_role=role)
        self.assertEqual(AccountingAssistant(self.service, authenticated_role="ADMIN").list_categories()[0]["id"], 1)
        self.assertEqual(self.service.writes, [])

    def test_list_filters_and_detail_reuse_service_without_write(self):
        assistant = AccountingAssistant(self.service, authenticated_role="ADMIN")
        result = assistant.list_entries(status="CONFIRMED", category_id=2, limit=10, offset=0)
        self.assertEqual(result["total"], 0)
        self.assertEqual(self.service.filters["category_id"], 2)
        self.assertEqual(self.service.filters["status"], "CONFIRMED")
        self.assertEqual(assistant.get_entry(7)["id"], 7)
        self.assertEqual(self.service.writes, [])

    def test_invalid_filter_is_rejected_before_service(self):
        assistant = AccountingAssistant(self.service, authenticated_role="ADMIN")
        with self.assertRaises(AccountingValidationError):
            assistant.list_entries(status="PENDING")
        self.assertIsNone(self.service.filters)

    def test_reversal_request_checks_reason_and_original_without_write(self):
        from datetime import date
        assistant = AccountingAssistant(self.service, authenticated_role="ADMIN")
        request = assistant.prepare_reversal(entry_id=7, operation_date=date(2026, 11, 3), reason=" Corrección ")
        self.assertEqual(request, {"entry_id": 7, "operation_date": "2026-11-03", "reason": "Corrección"})
        with self.assertRaises(AccountingValidationError):
            assistant.prepare_reversal(entry_id=7, operation_date=date(2026, 11, 3), reason=" ")
        self.service.entry_status = "REVERSED"
        replay_request = assistant.prepare_reversal(entry_id=7, operation_date=date(2026, 11, 3), reason="Corrección")
        self.assertEqual(replay_request["entry_id"], 7)
        self.assertEqual(self.service.writes, [])


if __name__ == "__main__":
    unittest.main()
