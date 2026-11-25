from datetime import date, timedelta
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orquestador.agentes.postventa import postventa_node


class Repository:
    def __init__(self):
        self.claims = []
        self.logistics = []

    def find_warranty(self, code):
        return {
            "id": 7, "customer_id": 41, "warranty_code": code,
            "status": "ACTIVE", "not_expired": True,
            "end_date": date.today() + timedelta(days=10),
            "item_or_service_name": "Laptop",
        }

    def list_customer_tickets(self, customer_id):
        assert customer_id == 41
        return [{"id": 11, "code": "TCK-11", "status": "IN_DIAGNOSIS"}]

    def create_warranty_claim(self, **values):
        self.claims.append(values)

    def create_logistics_record(self, **values):
        self.logistics.append(values)
        return 55


def test_orchestrator_warranty_status_uses_customer_ownership(monkeypatch):
    import app.agents.orquestador.agentes.warranty as warranty
    repository = Repository()
    monkeypatch.setattr(warranty, "ServiceRepository", lambda: repository)
    result = postventa_node({
        "user_id": 41, "warranty_status_pending": True, "warranty_code": "WAR-7",
        "messages": [HumanMessage(content="Estado de garantía")],
    })
    assert result["warranty_status"] == "ACTIVE"
    assert "vigente" in result["messages"][0].content


def test_orchestrator_claim_uses_owned_ticket_and_shared_policy(monkeypatch):
    import app.agents.orquestador.agentes.warranty as warranty
    repository = Repository()
    monkeypatch.setattr(warranty, "ServiceRepository", lambda: repository)
    monkeypatch.setattr(warranty, "new_claim_code", lambda: "CLM-TEST")
    result = postventa_node({
        "user_id": 41, "warranty_claim_pending": True,
        "warranty_code": "WAR-7", "ticket_code": "TCK-11",
        "messages": [HumanMessage(content="Se apaga al iniciar")],
    })
    assert result["warranty_claim_code"] == "CLM-TEST"
    assert repository.claims[0]["ticket_id"] == 11
    assert repository.claims[0]["customer_id"] == 41


def test_orchestrator_logistics_records_explicit_store_preference(monkeypatch):
    import app.agents.orquestador.agentes.logistics as logistics

    class Model:
        def with_structured_output(self, schema):
            return self
        def invoke(self, messages):
            return SimpleNamespace(
                mode="PHYSICAL_STORE", courier_company=None, shipping_address=None
            )

    repository = Repository()
    monkeypatch.setattr(logistics, "ServiceRepository", lambda: repository)
    monkeypatch.setattr(logistics, "create_chat_model", lambda: Model())
    result = postventa_node({
        "user_id": 41, "ticket_id": 11, "logistics_pending": True,
        "messages": [HumanMessage(content="Prefiero retiro presencial")],
    })
    assert result["logistics_record_id"] == 55
    assert repository.logistics[0]["mode"] == "PHYSICAL_STORE"
