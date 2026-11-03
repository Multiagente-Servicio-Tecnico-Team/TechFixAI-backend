from app.application.tickets import lookup_customer_ticket


class Repository:
    def __init__(self, rows):
        self.rows = rows
        self.customer_ids = []

    def list_customer_tickets(self, customer_id):
        self.customer_ids.append(customer_id)
        return self.rows


def test_ticket_lookup_matches_exact_code_only_with_authenticated_customer_scope():
    row = {"id": 3, "code": "TCK-ABC123", "status": "IN_DIAGNOSIS", "quote": None}
    repository = Repository([row])

    assert lookup_customer_ticket(repository, customer_id=41, ticket_code="tck-abc123") == row
    assert repository.customer_ids == [41]


def test_ticket_lookup_abstains_for_unknown_or_other_customer_ticket():
    repository = Repository([])

    assert lookup_customer_ticket(repository, customer_id=41, ticket_code="TCK-OTHER") is None
    assert repository.customer_ids == [41]
