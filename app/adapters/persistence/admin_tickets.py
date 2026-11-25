"""Adaptador de persistencia PostgreSQL para el panel administrativo de tickets."""
from app.application.ports import AdminTicketRepository
from app.database.repository import ServiceRepository


class AdminTicketRepositoryAdapter:
    """Expone el puerto administrativo reutilizando la sesión PostgreSQL existente."""

    def __init__(self, repository: AdminTicketRepository | None = None):
        self._repository = repository or ServiceRepository()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._repository, name)
