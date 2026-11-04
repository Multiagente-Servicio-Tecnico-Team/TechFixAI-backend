"""Nodo contador con servicio 003 simulado; sin base de datos ni proveedor externo."""
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.agents.decentralized.agents.accountant import accountant_node


class Service:
    def __init__(self):
        self.calls = []

    def list_categories(self):
        self.calls.append(("categories",))
        return [{"id": 3, "code": "OTHER", "name": "Otro"}]

    def list_entries(self, **filters):
        self.calls.append(("list", filters))
        return {"items": [{"id": 8, "status": "CONFIRMED", "operation_date": "2026-11-03", "concept": "Manual"}],
                "total": 1, "limit": filters["limit"], "offset": filters["offset"]}

    def get_entry(self, entry_id):
        self.calls.append(("detail", entry_id))
        return {"id": entry_id, "status": "CONFIRMED", "reversal_of_entry_id": None,
                "operation_date": "2026-11-03", "concept": "Manual", "detail": "Detalle",
                "debit_total": "10.00", "credit_total": "10.00", "currency": "PEN", "lines": []}

    def create_entry(self, **kwargs):
        raise AssertionError("El chat no puede crear asientos")

    def reverse_entry(self, **kwargs):
        raise AssertionError("El chat no puede ejecutar reversiones")


def invoke(message, role="ADMIN"):
    service = Service()
    result = accountant_node({"messages": [HumanMessage(content=message)]}, SimpleNamespace(context={
        "authenticated_role": role, "accounting_service_factory": lambda: service,
    }))
    return result["messages"][0].content, service.calls


def test_denies_other_roles_before_service_access():
    for role in (None, "CUSTOMER", "TECHNICIAN"):
        reply, calls = invoke("categorías contables", role)
        assert "ADMIN" in reply
        assert calls == []


def test_reads_real_categories_and_filtered_entries_from_service():
    reply, calls = invoke("categorías contables")
    assert "3: Otro (OTHER)" in reply
    assert calls == [("categories",)]
    reply, calls = invoke("listar asientos status=CONFIRMED limit=10 offset=0")
    assert "8 (CONFIRMED" in reply
    assert calls[0][0] == "list"
    assert calls[0][1]["status"] == "CONFIRMED"
    assert calls[0][1]["limit"] == 10


def test_detail_and_reversal_request_never_write():
    reply, calls = invoke("ver asiento 8")
    assert "Asiento 8" in reply
    assert calls == [("detail", 8)]
    reply, calls = invoke("revertir asiento 8 fecha=2026-11-03 motivo=Corrección manual")
    assert "no ejecuta la reversión" in reply
    assert calls == [("detail", 8)]


def test_missing_reversal_reason_does_not_write():
    reply, calls = invoke("revertir asiento 8")
    assert "motivo" in reply
    assert calls == []


def test_chat_confirmation_text_cannot_reverse_entry():
    reply, calls = invoke("confirmo revertir asiento 8 fecha=2026-11-03 motivo=Corrección manual")
    assert "no ejecuta la reversión" in reply
    assert calls == [("detail", 8)]


def test_unknown_list_filter_does_not_return_unfiltered_data():
    reply, calls = invoke("listar asientos supplier_id=5")
    assert "No se pudo completar" in reply
    assert calls == []
