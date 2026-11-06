"""Shared guard fixture only; lifecycle assertions live in sprint2 tests."""
from app.accounts.config import Settings
from types import SimpleNamespace
class Guard:
    settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False)
    def require_customer(self, request):
        return SimpleNamespace(id=1)
