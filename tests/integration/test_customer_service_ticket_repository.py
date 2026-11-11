from app.database.repository import ServiceRepository


class Result:
    def __init__(self, scalar=None): self.scalar = scalar
    def scalar_one(self): return self.scalar


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class Session:
    def __init__(self):
        self.calls = []
        self.results = [Result(42), Result(None), Result(17), Result(None)]
        self.transaction = Transaction()
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def begin(self): return self.transaction
    def execute(self, query, params):
        self.calls.append((str(query), params))
        return self.results.pop(0)


def test_manual_ticket_persists_customer_snapshot_and_admin_actor_separately():
    session = Session()
    repository = ServiceRepository(lambda: session)
    ticket_id = repository.create_admin_ticket(values={
        "customer_id": None, "contact_name": "Cliente Mostrador", "contact_phone": "987654321",
        "contact_email": "cliente@example.test", "technician_id": None, "title": "Laptop",
        "failure_description": "No enciende", "origin": "MANUAL", "advance_amount": None,
        "advance_payment_method": None, "request_type": "REPAIR", "diagnosis_type": "NONE",
        "status": "NEW", "hardware_diagnosis": None, "software_diagnosis": None,
        "estimated_labor_hours": 0, "is_remote_service": False,
    }, code="TCK-1", actor_id=7)
    assert ticket_id == 17
    assert "INSERT INTO customers" in session.calls[0][0]
    assert "INSERT INTO customer_audit_events" in session.calls[1][0]
    assert "commercial_customer_id" in session.calls[2][0]
    assert session.calls[2][1]["commercial_customer_id"] == 42
    assert session.calls[2][1]["actor_id"] == 7
    assert session.calls[3][1]["actor"] == 7
