from decimal import Decimal

from langchain_core.messages import HumanMessage

from app.agents.refund_requests import make_refund_agent


class Repository:
    def __init__(self):
        self.calls = []

    def find_payment_id_by_code(self, customer_id, payment_code):
        self.calls.append(("lookup", customer_id, payment_code))
        return 17

    def request_refund(self, **values):
        self.calls.append(("refund", values))
        return {"id": 3, "ticket_id": 8, "status": "REQUESTED"}


def test_refund_agent_asks_for_missing_payment_details_without_writing():
    repository = Repository()
    agent = make_refund_agent(repository)

    result = agent({"customer_id": 41, "messages": [HumanMessage(content="Quiero un reembolso")]})

    assert result["awaiting_refund_details"] is True
    assert "PAY-" in result["messages"][0].content
    assert repository.calls == []


def test_refund_agent_registers_only_pending_request_for_owned_payment():
    repository = Repository()
    agent = make_refund_agent(repository)

    result = agent({
        "customer_id": 41,
        "awaiting_refund_details": True,
        "messages": [HumanMessage(content="PAY-ABC123; importe: S/ 25.50; motivo: producto defectuoso")],
    })

    assert result["refund_status"] == "REQUESTED"
    assert result["awaiting_refund_details"] is False
    assert "revisión manual" in result["messages"][0].content.casefold()
    assert repository.calls == [
        ("lookup", 41, "PAY-ABC123"),
        ("refund", {
            "customer_id": 41,
            "payment_id": 17,
            "amount": Decimal("25.50"),
            "reason": "producto defectuoso",
        }),
    ]
