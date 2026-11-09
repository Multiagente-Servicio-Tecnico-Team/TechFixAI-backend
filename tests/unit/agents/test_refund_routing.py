from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized.graph import HANDOFF_TOOLS, build_graph
from app.agents.decentralized.support import support_node


class RefundRepository:
    def __init__(self):
        self.lookups = []
        self.requests = []

    def find_payment_id_by_code(self, customer_id, payment_code):
        self.lookups.append((customer_id, payment_code))
        return 19 if (customer_id, payment_code) == (41, "PAY-ABC123") else None

    def request_refund(self, **values):
        self.requests.append(values)
        return {"id": 27, "payment_id": 19, "ticket_id": 8,
                "amount": values["amount"], "status": "REQUESTED"}


def test_authenticated_refund_request_routes_to_shared_pending_handler():
    state = {
        "customer_id": 41,
        "messages": [HumanMessage(content=(
            "Solicito un reembolso: PAY-ABC123; importe: S/ 25.50; "
            "motivo: Equipo defectuoso."
        ))],
        "turn_start_index": 0,
        "handoff_count": 0,
        "handoff_history": [],
        "tool_iterations": {},
        "errors": [],
    }

    prepared = support_node(state, authenticated_customer_id=41)
    tool_call = prepared["messages"][0].tool_calls[0]

    assert tool_call["name"] == "transfer_to_refund"
    assert HANDOFF_TOOLS[tool_call["name"]] == "reembolsos"


def test_descentralized_graph_persists_only_a_customer_owned_pending_refund():
    repository = RefundRepository()
    graph = build_graph(
        checkpointer=MemorySaver(),
        ticket_repository=repository,
        ticket_writes=True,
        sales_quote_writes=True,
        sales_quote_repository=object(),
    )
    result = graph.invoke(
        {
            "customer_id": 41,
            "messages": [HumanMessage(content=(
                "Solicito un reembolso: PAY-ABC123; importe: S/ 25.50; "
                "motivo: Equipo defectuoso."
            ))],
        },
        config={"configurable": {"thread_id": "refund-contract-41"}},
        context={"authenticated_customer_id": 41},
    )

    assert result["outcome"] == "refund_requested"
    assert result["refund_status"] == "REQUESTED"
    assert repository.lookups == [(41, "PAY-ABC123")]
    assert len(repository.requests) == 1
    assert repository.requests[0]["customer_id"] == 41
    assert repository.requests[0]["payment_id"] == 19
    assert repository.requests[0]["reason"] == "Equipo defectuoso."
    assert str(repository.requests[0]["amount"]) == "25.50"
    assert "No se ejecutó ningún pago" in result["messages"][-1].content


def test_refund_request_without_trusted_customer_identity_does_not_route():
    result = support_node({
        "customer_id": 99,
        "messages": [HumanMessage(content="Solicito un reembolso")],
    })

    assert result["messages"][0].tool_calls[0]["name"] == "transfer_to_refund"


def test_unauthenticated_complete_refund_does_not_read_or_write_payment():
    from app.agents.refund_requests import make_refund_agent

    class Repository:
        def find_payment_id_by_code(self, *_args): raise AssertionError("No payment lookup without session")
        def request_refund(self, **_values): raise AssertionError("No refund write without session")

    result = make_refund_agent(Repository())({
        "messages": [HumanMessage(content=(
            "PAY-ABC123; importe: S/ 25.50; motivo: Equipo defectuoso."
        ))],
    })
    assert result["awaiting_refund_details"] is True
    assert not result.get("refund_id")
    assert "inicia sesion" in result["messages"][0].content.lower()
