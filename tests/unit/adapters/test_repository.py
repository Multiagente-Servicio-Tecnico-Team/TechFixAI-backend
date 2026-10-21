import unittest
from decimal import Decimal

from app.database.repository import ServiceRepository


class FakeResult:
    def __init__(
        self,
        *,
        row=None,
        rows=None,
        scalar=None,
        rowcount=1,
        error: Exception | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.scalar = scalar
        self.rowcount = rowcount
        self.error = error

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row

    def scalar_one(self):
        if self.error:
            raise self.error
        return self.scalar

    def scalar_one_or_none(self):
        if self.error:
            raise self.error
        return self.scalar

    def __iter__(self):
        return iter(self.rows)


class FakeTransaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type:
            self.rolled_back = True
        else:
            self.committed = True
        return False


class FakeSession:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []
        self.transaction = FakeTransaction()

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        return False

    def begin(self):
        return self.transaction

    def execute(self, query, parameters):
        self.calls.append((str(query), parameters))
        return self.results.pop(0)


class RepositoryTests(unittest.TestCase):
    def test_customer_lookup_uses_email_bind_parameter_and_customer_role(self):
        session = FakeSession(
            [FakeResult(row={"id": 9, "name": "Ana", "last_name": "Prueba"})]
        )
        repository = ServiceRepository(lambda: session)

        customer = repository.find_customer("  ANA@example.com ")

        self.assertEqual(customer["id"], 9)
        query, parameters = session.calls[0]
        self.assertIn("role::text = 'CUSTOMER'", query)
        self.assertIn(":email", query)
        self.assertEqual(parameters, {"email": "ANA@example.com"})

    def test_spare_part_lookup_matches_catalog_names_with_underscore_identifiers(self):
        session = FakeSession(
            [
                FakeResult(
                    rows=[
                        {
                            "id": 3,
                            "code": "SVC-001",
                            "name": "Servicio Mantenimiento Contactos",
                        }
                    ]
                )
            ]
        )
        repository = ServiceRepository(lambda: session)

        parts = repository.find_spare_parts("Servicio_Mantenimiento_Contactos")

        self.assertEqual(parts[0]["id"], 3)
        query, parameters = session.calls[0]
        self.assertIn("LOWER(code) = LOWER(:term)", query)
        self.assertIn("LOWER(name) = LOWER(:normalized_name)", query)
        self.assertIn("ILIKE :pattern ESCAPE '!'", query)
        self.assertEqual(
            parameters["normalized_name"],
            "Servicio Mantenimiento Contactos",
        )
        self.assertEqual(
            parameters["pattern"],
            "%Servicio Mantenimiento Contactos%",
        )

    def test_spare_part_alternatives_lookup_uses_family_token(self):
        session = FakeSession(
            [
                FakeResult(
                    rows=[
                        {
                            "id": 19,
                            "code": "SSD_500GB",
                            "name": "SSD 500 GB",
                            "unit_price": Decimal("45.00"),
                            "current_stock": 3,
                        }
                    ]
                )
            ]
        )
        repository = ServiceRepository(lambda: session)

        alternatives = repository.find_spare_part_alternatives("SSD_1TB")

        self.assertEqual(alternatives[0]["code"], "SSD_500GB")
        query, parameters = session.calls[0]
        self.assertIn("code ILIKE :pattern", query)
        self.assertIn("name ILIKE :pattern", query)
        self.assertEqual(parameters, {"pattern": "%SSD%"})

    def test_ram_alternatives_are_scoped_to_memory_categories(self):
        session = FakeSession([FakeResult(rows=[])])
        repository = ServiceRepository(lambda: session)

        repository.find_spare_part_alternatives("RAM_16GB")

        query, parameters = session.calls[0]
        self.assertIn("category ILIKE 'RAM%'", query)
        self.assertIn("name ILIKE 'Memoria RAM%'", query)
        self.assertNotIn("name ILIKE '%RAM%'", query)
        self.assertEqual(parameters, {"pattern": "%RAM%"})

    def test_battery_alternatives_exclude_cmos_and_rtc_cells(self):
        session = FakeSession([FakeResult(rows=[])])
        repository = ServiceRepository(lambda: session)

        repository.find_spare_part_alternatives("REP-BAT-L2023")

        query, _ = session.calls[0]
        self.assertIn("name NOT ILIKE '%RTC%'", query)
        self.assertIn("name NOT ILIKE '%CMOS%'", query)

    def test_ticket_insert_uses_parameters_and_starts_in_diagnosis(self):
        session = FakeSession([FakeResult(scalar=55)])
        repository = ServiceRepository(lambda: session)

        ticket_id = repository.create_ticket(
            code="ST-123456789ABC",
            customer_id=9,
            title="Laptop falla",
            failure_description="Se apaga.",
            request_type="REPAIR",
            provisional_diagnosis="Ventilación.",
        )

        query, parameters = session.calls[0]
        self.assertEqual(ticket_id, 55)
        self.assertIn("IN_DIAGNOSIS", query)
        self.assertIn(":failure_description", query)
        self.assertEqual(parameters["customer_id"], 9)
        self.assertTrue(session.transaction.committed)

    def test_service_intake_ticket_starts_new(self):
        session = FakeSession([FakeResult(scalar=55)])
        repository = ServiceRepository(lambda: session)

        ticket_id = repository.create_intake_ticket(
            code="TCK-123456789ABC",
            customer_id=9,
            title="Laptop falla",
            failure_description="Se apaga.",
            request_type="REPAIR",
        )

        query, parameters = session.calls[0]
        self.assertEqual(ticket_id, 55)
        self.assertIn("CAST('NEW' AS ticket_status_enum)", query)
        self.assertEqual(parameters["request_type"], "REPAIR")
        self.assertTrue(session.transaction.committed)

    def test_service_diagnosis_updates_existing_ticket_columns(self):
        session = FakeSession([FakeResult(scalar=55)])
        repository = ServiceRepository(lambda: session)

        repository.update_ticket_diagnosis(
            ticket_id=55,
            customer_id=9,
            diagnosis="Posible falla de ventilación.",
            diagnosis_type="HARDWARE",
        )

        query, parameters = session.calls[0]
        self.assertIn("UPDATE tickets", query)
        self.assertIn("hardware_diagnosis = :hardware_diagnosis", query)
        self.assertIn("software_diagnosis = :software_diagnosis", query)
        self.assertIn("CAST('IN_DIAGNOSIS' AS ticket_status_enum)", query)
        self.assertEqual(parameters["hardware_diagnosis"], "Posible falla de ventilación.")
        self.assertIsNone(parameters["software_diagnosis"])
        self.assertEqual(parameters["ticket_id"], 55)
        self.assertEqual(parameters["customer_id"], 9)
        self.assertTrue(session.transaction.committed)

    def test_software_service_diagnosis_uses_software_column(self):
        session = FakeSession([FakeResult(scalar=55)])
        repository = ServiceRepository(lambda: session)

        repository.update_ticket_diagnosis(
            ticket_id=55,
            customer_id=9,
            diagnosis="Posible incompatibilidad de software.",
            diagnosis_type="SOFTWARE",
        )

        parameters = session.calls[0][1]
        self.assertIsNone(parameters["hardware_diagnosis"])
        self.assertEqual(
            parameters["software_diagnosis"],
            "Posible incompatibilidad de software.",
        )

    def test_accepted_repair_quote_creates_pending_payment_atomically(self):
        session = FakeSession(
            [
                FakeResult(),
                FakeResult(scalar=77),
                FakeResult(
                    row={
                        "id": 88,
                        "payment_code": "PAY-TEST",
                        "amount": Decimal("50.00"),
                        "status": "PENDING",
                    }
                ),
                FakeResult(rowcount=1),
            ]
        )
        repository = ServiceRepository(lambda: session)

        result = repository.accept_ticket_quote(
            ticket_id=55,
            customer_id=9,
            quote_type="REPAIR",
            labor_cost=Decimal("50.00"),
            parts_cost=Decimal("0.00"),
            total_amount=Decimal("50.00"),
            observations="Cotización aceptada.",
            parts=[],
            payment_code="PAY-TEST",
        )

        self.assertEqual(result["quote_id"], 77)
        self.assertEqual(result["payment_id"], 88)
        self.assertEqual(result["payment_code"], "PAY-TEST")
        self.assertIn("ACCEPTED", session.calls[1][0])
        self.assertIn("PENDING", session.calls[2][0])
        self.assertIn("PAYMENT_PENDING", session.calls[3][0])
        self.assertTrue(session.transaction.committed)

    def test_quote_and_ticket_update_share_one_transaction(self):
        session = FakeSession(
            [
                FakeResult(rowcount=1),
                FakeResult(scalar=77),
                FakeResult(),
            ]
        )
        repository = ServiceRepository(lambda: session)

        quote_id = repository.save_quote(
            ticket_id=55,
            labor_cost=Decimal("80.00"),
            parts_cost=Decimal("10.00"),
            total_amount=Decimal("90.00"),
            observations="Diagnóstico provisional.",
            parts=[
                {
                    "id": 4,
                    "quantity": 1,
                    "unit_price": Decimal("10.00"),
                    "subtotal": Decimal("10.00"),
                }
            ],
        )

        self.assertEqual(quote_id, 77)
        self.assertEqual(len(session.calls), 3)
        self.assertIn("QUOTED", session.calls[0][0])
        self.assertIn("quotes", session.calls[1][0])
        self.assertIn("quote_details", session.calls[2][0])
        self.assertTrue(session.transaction.committed)

    def test_quote_transaction_rolls_back_when_ticket_is_missing(self):
        session = FakeSession([FakeResult(rowcount=0)])
        repository = ServiceRepository(lambda: session)

        with self.assertRaisesRegex(LookupError, "ticket 55"):
            repository.save_quote(
                ticket_id=55,
                labor_cost=Decimal("80.00"),
                parts_cost=Decimal("0.00"),
                total_amount=Decimal("80.00"),
                observations="Diagnóstico provisional.",
                parts=[],
            )

        self.assertEqual(len(session.calls), 1)
        self.assertTrue(session.transaction.rolled_back)
        self.assertFalse(session.transaction.committed)

    def test_ticket_and_quote_are_created_in_one_transaction(self):
        session = FakeSession(
            [
                FakeResult(scalar=55),
                FakeResult(scalar=77),
                FakeResult(rowcount=1),
                FakeResult(),
            ]
        )
        repository = ServiceRepository(lambda: session)

        ticket_id, quote_id = repository.create_ticket_with_quote(
            ticket_code="ST-123456789ABC",
            customer_id=9,
            title="Laptop lenta",
            failure_description="Tarda en iniciar.",
            request_type="REPAIR",
            provisional_diagnosis="Unidad lenta.",
            labor_cost=Decimal("20.00"),
            parts_cost=Decimal("180.00"),
            total_amount=Decimal("200.00"),
            observations="Guía RAG simulada.",
            parts=[
                {
                    "id": 4,
                    "quantity": 1,
                    "unit_price": Decimal("180.00"),
                    "subtotal": Decimal("180.00"),
                }
            ],
        )

        self.assertEqual((ticket_id, quote_id), (55, 77))
        self.assertEqual(len(session.calls), 4)
        self.assertIn("IN_DIAGNOSIS", session.calls[0][0])
        self.assertIn("hardware_diagnosis", session.calls[0][0])
        self.assertIn("software_diagnosis", session.calls[0][0])
        self.assertNotIn("provisional_diagnosis", session.calls[0][0])
        self.assertEqual(session.calls[0][1]["hardware_diagnosis"], "Unidad lenta.")
        self.assertIsNone(session.calls[0][1]["software_diagnosis"])
        self.assertIn("quotes", session.calls[1][0])
        self.assertIn("QUOTED", session.calls[2][0])
        self.assertIn("quote_details", session.calls[3][0])
        self.assertTrue(session.transaction.committed)

    def test_software_diagnosis_uses_software_ticket_column(self):
        session = FakeSession(
            [
                FakeResult(scalar=55),
                FakeResult(scalar=77),
                FakeResult(rowcount=1),
            ]
        )
        repository = ServiceRepository(lambda: session)

        repository.create_ticket_with_quote(
            ticket_code="ST-123456789ABC",
            customer_id=9,
            title="Error de sistema",
            failure_description="La aplicación se cierra.",
            request_type="SUPPORT",
            provisional_diagnosis="Posible incompatibilidad.",
            labor_cost=Decimal("50.00"),
            parts_cost=Decimal("0.00"),
            total_amount=Decimal("50.00"),
            observations="Tipo de mano de obra: diagnosis",
            parts=[],
            diagnosis_type="SOFTWARE",
        )

        ticket_parameters = session.calls[0][1]
        self.assertIsNone(ticket_parameters["hardware_diagnosis"])
        self.assertEqual(
            ticket_parameters["software_diagnosis"],
            "Posible incompatibilidad.",
        )

    def test_logistics_preference_is_updated_while_receipt_is_pending(self):
        session = FakeSession(
            [
                FakeResult(
                    row={
                        "id": 81,
                        "mode": "PHYSICAL_STORE",
                        "status": "PENDING_RECEIPT",
                        "courier_company": None,
                        "shipping_address": None,
                    }
                ),
                FakeResult(scalar=81),
            ]
        )
        repository = ServiceRepository(lambda: session)

        record_id = repository.create_logistics_record(
            ticket_id=55,
            customer_id=9,
            mode="COURIER_SHIPMENT",
            courier_company="Courier de prueba",
            shipping_address="Dirección de prueba",
        )

        self.assertEqual(record_id, 81)
        self.assertIn("UPDATE logistics_records", session.calls[1][0])
        self.assertTrue(session.transaction.committed)

    def test_logistics_preference_cannot_change_after_receipt(self):
        session = FakeSession(
            [
                FakeResult(
                    row={
                        "id": 81,
                        "mode": "PHYSICAL_STORE",
                        "status": "RECEIVED_AT_WORKSHOP",
                        "courier_company": None,
                        "shipping_address": None,
                    }
                )
            ]
        )
        repository = ServiceRepository(lambda: session)

        with self.assertRaisesRegex(ValueError, "después de la recepción"):
            repository.create_logistics_record(
                ticket_id=55,
                customer_id=9,
                mode="COURIER_SHIPMENT",
                courier_company="Courier de prueba",
                shipping_address="Dirección de prueba",
            )

        self.assertEqual(len(session.calls), 1)
        self.assertTrue(session.transaction.rolled_back)

    def test_diagnostic_quote_can_be_saved_without_spare_part_details(self):
        session = FakeSession(
            [
                FakeResult(scalar=55),
                FakeResult(scalar=77),
                FakeResult(rowcount=1),
            ]
        )
        repository = ServiceRepository(lambda: session)

        ticket_id, quote_id = repository.create_ticket_with_quote(
            ticket_code="ST-123456789ABC",
            customer_id=9,
            title="Falla sin identificar",
            failure_description="El equipo no inicia.",
            request_type="REPAIR",
            provisional_diagnosis="Requiere diagnóstico.",
            labor_cost=Decimal("50.00"),
            parts_cost=Decimal("0.00"),
            total_amount=Decimal("50.00"),
            observations="Tipo de mano de obra: diagnosis",
            parts=[],
        )

        self.assertEqual((ticket_id, quote_id), (55, 77))
        self.assertEqual(len(session.calls), 3)
        self.assertIn("quotes", session.calls[1][0])
        self.assertEqual(
            session.calls[1][1]["labor_cost"],
            Decimal("50.00"),
        )
        self.assertEqual(
            session.calls[1][1]["parts_cost"],
            Decimal("0.00"),
        )
        self.assertEqual(
            session.calls[1][1]["total_amount"],
            Decimal("50.00"),
        )
        self.assertNotIn("quote_details", "\n".join(query for query, _ in session.calls))
        self.assertIn("QUOTED", session.calls[2][0])
        self.assertTrue(session.transaction.committed)

    def test_ticket_is_rolled_back_if_quote_insert_fails(self):
        session = FakeSession(
            [
                FakeResult(scalar=55),
                FakeResult(error=RuntimeError("simulated quote failure")),
            ]
        )
        repository = ServiceRepository(lambda: session)

        with self.assertRaisesRegex(RuntimeError, "simulated quote failure"):
            repository.create_ticket_with_quote(
                ticket_code="ST-123456789ABC",
                customer_id=9,
                title="Laptop lenta",
                failure_description="Tarda en iniciar.",
                request_type="REPAIR",
                provisional_diagnosis="Unidad lenta.",
                labor_cost=Decimal("20.00"),
                parts_cost=Decimal("0.00"),
                total_amount=Decimal("20.00"),
                observations="Guía RAG simulada.",
                parts=[],
            )

        self.assertEqual(len(session.calls), 2)
        self.assertTrue(session.transaction.rolled_back)
        self.assertFalse(session.transaction.committed)


if __name__ == "__main__":
    unittest.main()
