from types import SimpleNamespace

from app.application.customer_profiles import CustomerProfileService


class CustomerRepository:
    def __init__(self):
        self.profile = None
        self.created = []

    def find_by_user_id(self, user_id):
        return self.profile

    def create_portal_profile(self, *, user_id, display_name, phone, email):
        self.created.append((user_id, display_name, phone, email))
        self.profile = {"id": 41, "user_id": user_id, "origin": "PORTAL"}
        return self.profile


def test_portal_customer_is_resolved_from_authenticated_user_not_payload():
    repository = CustomerRepository()
    service = CustomerProfileService(repository)
    authenticated = SimpleNamespace(id=7, role="CUSTOMER", first_name="Ana", last_name="Rojas", phone="3001234567", email="ana@example.com")
    profile = service.resolve_session_customer(authenticated)
    assert profile["id"] == 41
    assert repository.created == [(7, "Ana Rojas", "3001234567", "ana@example.com")]
