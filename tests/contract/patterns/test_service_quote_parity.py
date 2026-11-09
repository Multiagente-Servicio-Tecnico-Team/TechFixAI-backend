from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.adapters.patterns.decentralized import DecentralizedPattern
from app.agents.decentralized.sales import sales_node
from app.application.chat_service_quotes import accept_chat_service_quote
from app.domain.errors import StaleQuote


class ServiceQuoteWriter:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def accept_ticket_quote(self, **values):
        self.calls.append(values)
        if self.error:
            raise self.error
        return {
            "quote_id": 71,
            "payment_id": 81,
            "payment_code": values["payment_code"],
            "payment_status": "PENDING",
        }


def _service_proposal():
    return {
        "status": "proposed",
        "currency": "PEN",
        "labor_total": "35.00",
        "known_parts_subtotal": "20.00",
        "total": "55.00",
        "parts": [{
            "inventory_id": 17,
            "code": "FAN-01",
            "name": "Ventilador de repuesto",
            "quantity": 1,
            "stock": 2,
            "unit_price": "20.00",
            "subtotal": "20.00",
            "available": True,
        }],
    }


@pytest.mark.parametrize("request_type", ["REPAIR", "SUPPORT"])
def test_decentralized_explicit_service_acceptance_persists_on_owned_ticket(request_type):
    writer = ServiceQuoteWriter()
    state = {
        "messages": [HumanMessage(content="Sí, confirmo")],
        "customer_id": 41,
        "ticket_id": 31,
        "ticket_code": "TCK-31",
        "request_type": request_type,
        "quote_task_type": "maintenance",
        "quote_status": "PENDING",
        "quote": _service_proposal(),
    }

    result = sales_node(
        state,
        authenticated_customer_id=41,
        service_quote_repository=writer,
    )

    assert len(writer.calls) == 1
    assert writer.calls[0]["customer_id"] == 41
    assert writer.calls[0]["ticket_id"] == 31
    assert writer.calls[0]["quote_type"] == "REPAIR"
    assert writer.calls[0]["total_amount"] == Decimal("55.00")
    assert result["quote_status"] == "ACCEPTED"
    assert result["quote_id"] == 71 and result["payment_id"] == 81
    assert "pendiente" in result["messages"][0].content.lower()
    assert "se ha reservado inventario" in result["messages"][0].content.lower()


def test_decentralized_service_quote_reject_and_owner_mismatch_do_not_write():
    proposal = _service_proposal()
    writer = ServiceQuoteWriter()
    rejected = sales_node({
        "messages": [HumanMessage(content="No, rechazo")], "customer_id": 41,
        "ticket_id": 31, "request_type": "REPAIR", "quote_status": "PENDING",
        "quote": proposal,
    }, authenticated_customer_id=41, service_quote_repository=writer)
    assert rejected["quote_status"] == "REJECTED"
    assert writer.calls == []

    unauthorized = sales_node({
        "messages": [HumanMessage(content="Sí, confirmo")], "customer_id": 41,
        "ticket_id": 31, "request_type": "REPAIR", "quote_status": "PENDING",
        "quote": proposal,
    }, authenticated_customer_id=42, service_quote_repository=writer)
    assert "pertenezca" in unauthorized["messages"][0].content.lower()
    assert writer.calls == []


def test_decentralized_stale_service_price_does_not_claim_acceptance():
    writer = ServiceQuoteWriter(StaleQuote())
    result = sales_node({
        "messages": [HumanMessage(content="Acepto")], "customer_id": 41,
        "ticket_id": 31, "request_type": "REPAIR", "quote_status": "PENDING",
        "quote": _service_proposal(),
    }, authenticated_customer_id=41, service_quote_repository=writer)
    assert result.get("quote_id") is None
    assert result["quote"]["status"] == "incomplete"
    assert "no se registró" in result["messages"][0].content.lower()


def test_service_quote_can_be_returned_before_a_database_quote_id_exists():
    result = {
        "messages": [AIMessage(content="Cotización de servicio pendiente")],
        "ticket_code": "TCK-31",
        "ticket_status": "IN_DIAGNOSIS",
        "quote_status": "PENDING",
        "quote": _service_proposal(),
    }
    response = DecentralizedPattern().to_reply(result)
    assert response.pending_quote is True
    assert response.quote is not None
    assert response.quote.status == "proposed"
    assert response.quote.total == Decimal("55.00")
    assert response.quote_id is None
    assert response.ticket is not None and response.ticket.code == "TCK-31"


def test_shared_service_quote_writer_recalculates_line_totals_before_persistence():
    writer = ServiceQuoteWriter()
    result = accept_chat_service_quote(
        writer=writer,
        customer_id=41,
        ticket_id=31,
        draft={**_service_proposal(), "labor_task_type": "maintenance"},
        payment_code="PAY-SERVICE-01",
    )
    assert result["payment_status"] == "PENDING"
    assert writer.calls[0]["parts_cost"] == Decimal("20.00")

    with pytest.raises(ValueError):
        accept_chat_service_quote(
            writer=writer,
            customer_id=41,
            ticket_id=31,
            draft={**_service_proposal(), "total": "1.00", "labor_task_type": "maintenance"},
            payment_code="PAY-SERVICE-02",
        )


class ServiceQuoteWriteBoundary:
    """Captures the repository write each customer graph must make on acceptance."""

    def __init__(self):
        self.accepted_ticket_quotes = []
        self.created_ticket_quotes = []

    def accept_ticket_quote(self, **values):
        self.accepted_ticket_quotes.append(values)
        return {
            "quote_id": 71,
            "payment_id": 81,
            "payment_code": values["payment_code"],
            "payment_status": "PENDING",
        }

    def create_accepted_ticket_quote(self, **values):
        self.created_ticket_quotes.append(values)
        return {
            "ticket_id": 31,
            "ticket_code": "TCK-31",
            "quote_id": 71,
            "payment_id": 81,
            "payment_code": values["payment_code"],
            "payment_status": "PENDING",
            "total_amount": values["total_amount"],
        }


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_each_customer_pattern_persists_accepted_service_quote_for_authenticated_ticket(
    pattern_id, monkeypatch
):
    writer = ServiceQuoteWriteBoundary()
    quote = {
        "quote_type": "REPAIR",
        "labor_task_type": "maintenance",
        "labor_cost": Decimal("35.00"),
        "parts_cost": Decimal("0.00"),
        "total_amount": Decimal("35.00"),
        "parts": [],
    }

    if pattern_id == "hierarchical":
        from app.agents.jerarquico.agents.billing import make_billing_agent

        result = make_billing_agent(writer)({
            "customer_id": 41,
            "ticket_id": 31,
            "ticket_code": "TCK-31",
            "request_type": "REPAIR",
            "quote_type": "REPAIR",
            "quote": quote,
        })
    elif pattern_id == "orchestrator":
        from app.agents.orquestador.agentes import ventas as orchestrator_sales

        monkeypatch.setattr(orchestrator_sales, "sales_repository", writer)
        result = orchestrator_sales.persistencia_node({
            "user_id": 41,
            "product": "Laptop",
            "category": "Soporte tÃ©cnico",
            "symptoms": "No enciende",
            "diagnosis": "RevisiÃ³n tÃ©cnica requerida",
            "labor_task_type": "maintenance",
            "labor_cost": Decimal("35.00"),
            "available_parts": [],
            "parts_total": Decimal("0.00"),
            "total": Decimal("35.00"),
            "ticket_confirmed": True,
        })
    else:
        result = sales_node({
            "messages": [HumanMessage(content="Acepto")],
            "customer_id": 41,
            "ticket_id": 31,
            "ticket_code": "TCK-31",
            "request_type": "REPAIR",
            "quote_task_type": "maintenance",
            "quote_status": "PENDING",
            "quote": {
                "status": "proposed",
                "currency": "PEN",
                "labor_total": "35.00",
                "known_parts_subtotal": "0.00",
                "total": "35.00",
                "parts": [],
            },
        }, authenticated_customer_id=41, service_quote_repository=writer)

    write = (writer.created_ticket_quotes[0] if writer.created_ticket_quotes
             else writer.accepted_ticket_quotes[0])
    assert write["customer_id"] == 41
    assert write["quote_type"] == "REPAIR"
    assert write["total_amount"] == Decimal("35.00")
    assert result["quote_id"] == 71
    assert result["payment_code"]
    assert result["ticket_status"] == "PAYMENT_PENDING"
    assert "pendiente" in result["messages"][0].content.casefold()
