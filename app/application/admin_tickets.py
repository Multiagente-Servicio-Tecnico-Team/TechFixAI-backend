"""Casos de uso administrativos sobre tickets y cotizaciones."""
from app.application.ports import AdminTicketRepository


class AdminTicketService:
    def __init__(self, repository: AdminTicketRepository):
        self.repository = repository

    def list_tickets(self, **filters):
        return self.repository.list_admin_tickets(**filters)

    def get_ticket(self, ticket_id: int):
        return self.repository.get_admin_ticket(ticket_id)

    def audit_events(self, ticket_id: int):
        return self.repository.list_ticket_audit_events(ticket_id)

    def create_manual_ticket(self, *, values, code: str, actor_id: int):
        return self.repository.create_admin_ticket(values=values, code=code, actor_id=actor_id)

    def update_ticket(self, *, ticket_id: int, values, actor_id: int):
        return self.repository.update_admin_ticket_audited(ticket_id, values, actor_id)

    def create_quote(self, **values):
        return self.repository.create_admin_ticket_quote(**values)
