"""Perfiles comerciales en memoria para las pruebas de chat (nunca usan la BD de .env)."""


class InMemoryCustomerProfiles:
    """Cumple lo que usa CustomerProfileService.resolve_session_customer."""

    def __init__(self):
        self.profiles: dict[int, dict] = {}

    def find_by_user_id(self, user_id: int):
        return self.profiles.get(user_id)

    def create_portal_profile(self, *, user_id: int, display_name: str, phone: str, email: str | None):
        return self.profiles.setdefault(user_id, {
            "id": 1000 + user_id, "display_name": display_name, "phone": phone, "email": email,
            "origin": "PORTAL", "user_id": user_id, "active": True,
        })


def customer_profiles_factory():
    """Una sola instancia por app, para que el perfil se conserve entre peticiones."""
    profiles = InMemoryCustomerProfiles()
    return lambda: profiles
