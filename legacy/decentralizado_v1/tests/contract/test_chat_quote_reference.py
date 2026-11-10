from decimal import Decimal

from app.adapters.api.chat import chat_out
from app.adapters.patterns.decentralized import DecentralizedPattern
from app.domain.chat import PatternReply, Quote, QuoteLine


def test_chat_response_exposes_persisted_quote_id_without_ticket():
    response = chat_out(
        "conversation-1",
        "hierarchical",
        PatternReply(
            reply="La cotización quedó pendiente.",
            quote=Quote(
                status="proposed",
                lines=(QuoteLine("SSD 1 TB", Decimal("250.00")),),
                total=Decimal("250.00"),
            ),
            quote_id=42,
        ),
    )

    assert response.quote_id == 42
    assert response.ticket is None
    assert response.quote.status == "proposed"


def test_decentralized_direct_sale_reply_keeps_quote_id_and_has_no_ticket():
    from langchain_core.messages import AIMessage

    result = {
        "quote_id": 77,
        "quote_status": "proposed",
        "quote": {
            "quote_type": "DIRECT_SALE",
            "total_amount": Decimal("250.00"),
            "parts": [{"name": "SSD 1 TB", "quantity": 1, "subtotal": Decimal("250.00")}],
        },
        "ticket_code": None,
        "messages": [AIMessage(content="Cotización pendiente.")],
    }
    reply = DecentralizedPattern().to_reply(result)

    assert reply.quote_id == 77
    assert reply.pending_quote is True
    assert reply.ticket is None
