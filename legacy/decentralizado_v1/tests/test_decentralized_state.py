"""Contratos en memoria; no importan clientes ni ejecutan servicios o SQL."""
from copy import deepcopy
from decimal import Decimal
from typing import get_args, get_type_hints

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.message import add_messages

from app.agents.decentralized import state as contracts


@pytest.mark.parametrize("intent", ["REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"])
def test_intencion_operativa_conserva_enum_real(intent):
    assert contracts.request_type_for_intent(intent) == intent


@pytest.mark.parametrize("intent", ["INFO_QUERY", "WARRANTY_STATUS_CHECK", "REFUND"])
def test_intenciones_sin_request_type_no_se_fuerzan(intent):
    assert contracts.request_type_for_intent(intent) is None
    assert intent not in get_args(contracts.RequestType)


def test_intencion_desconocida_se_rechaza():
    with pytest.raises(ValueError, match="Intención"):
        contracts.request_type_for_intent("INVENTADO")


def test_enums_sql_exactos_y_estados_de_herramienta_separados():
    expected = {
        "RequestType": "REPAIR SALE PC_BUILD SUPPORT WARRANTY_CLAIM",
        "DiagnosisType": "HARDWARE SOFTWARE HYBRID NONE",
        "TicketStatus": "NEW IN_DIAGNOSIS QUOTED PAYMENT_PENDING PAID IN_REPAIR READY_FOR_DELIVERY DELIVERED CANCELLED WARRANTY_IN_REVIEW",
        "QuoteType": "REPAIR DIRECT_SALE PC_BUILD",
        "QuoteStatus": "PENDING ACCEPTED REJECTED EXPIRED",
        "PaymentStatus": "PENDING COMPLETED FAILED REFUNDED PARTIALLY_REFUNDED",
        "PaymentMethod": "CREDIT_CARD DEBIT_CARD BANK_TRANSFER CASH PAYMENT_GATEWAY",
        "RefundStatus": "REQUESTED APPROVED PROCESSED REJECTED",
        "LogisticsMode": "PHYSICAL_STORE COURIER_SHIPMENT",
        "LogisticsStatus": "PENDING_RECEIPT RECEIVED_AT_WORKSHOP READY_FOR_DISPATCH IN_TRANSIT DELIVERED FAILED_DELIVERY",
        "WarrantyStatus": "ACTIVE EXPIRED VOIDED CLAIMED",
        "WarrantyClaimStatus": "IN_REVIEW APPROVED_REPAIR APPROVED_REPLACEMENT APPROVED_REFUND REJECTED",
    }
    for name, values in expected.items():
        assert set(get_args(getattr(contracts, name))) == set(values.split())
    assert "PRICE_UNAVAILABLE" not in get_args(contracts.PaymentStatus)
    assert "AVAILABLE" not in get_args(contracts.TicketStatus)


def test_estado_legacy_opcional_y_reductor_conservados():
    hints = get_type_hints(contracts.AgentState, include_extras=True)
    legacy = {"messages", "turn_start_index", "quote_scope", "quote", "inventory_query",
              "current_agent", "next_agent", "handoff_history", "handoff_count",
              "tool_iterations", "required_parts", "inventory_pending", "inventory_results", "errors"}
    assert legacy <= hints.keys()
    assert contracts.AgentState.__required_keys__ == frozenset()
    assert get_args(hints["messages"])[1] is add_messages
    assert {"soporte", "tecnico", "ventas", "almacen"} <= set(get_args(contracts.AgentName))
    assert len(get_args(contracts.AgentName)) == 9
    # El contrato no fabrica IDs ni rellena datos persistidos por defecto.
    legacy_state = contracts.AgentState(messages=[HumanMessage(content="Consulta")])
    assert "customer_id" not in legacy_state and "ticket_id" not in legacy_state


def accepted_state():
    return contracts.AgentState(
        messages=[HumanMessage(content="Acepto la propuesta vigente")],
        customer_id=12, ticket_id=7, ticket_code="TCK-PRUEBA",
        ticket_status="NEW", intent="SALE", request_type="SALE",
        intake={"budget": Decimal("200.00"), "currency": "PEN"},
        requested_items=[{"name": "SSD de prueba", "quantity": 1}],
        request_revision=2, inventory_revision=2, inventory_pending=False,
        inventory_results=[{"stock": 1}],
        proposal={"request_revision": 2, "quote_type": "DIRECT_SALE", "currency": "PEN",
                  "labor_cost": Decimal("0.00"), "parts_cost": Decimal("180.00"),
                  "total_amount": Decimal("180.00"),
                  "lines": [{"spare_part_id": 1, "custom_item_name": None, "quantity": 1,
                             "unit_price": Decimal("180.00"), "subtotal": Decimal("180.00")}]},
        proposal_decision={"request_revision": 2, "accepted": True, "explicit": True},
        quote={"total": "180.00"}, quote_id=9, quote_status="ACCEPTED",
        payment_id=10, payment_code="PAY-PRUEBA", payment={"status": "PENDING"},
        warranty_id=11, warranty_code="WAR-PRUEBA", warranty={"status": "ACTIVE"},
    )


def test_aceptacion_explicita_de_revision_vigente():
    assert contracts.proposal_is_accepted(accepted_state())
    assert not contracts.proposal_is_accepted({})


@pytest.mark.parametrize("field,value", [
    ("request_revision", 3), ("request_revision", True),
    ("inventory_revision", 1), ("inventory_revision", None),
    ("inventory_pending", True), ("proposal", None), ("proposal_decision", None),
    ("proposal_decision", {"request_revision": 1, "accepted": True, "explicit": True}),
    ("proposal_decision", {"request_revision": 2, "accepted": False, "explicit": True}),
    ("proposal_decision", {"request_revision": 2, "accepted": True, "explicit": False}),
    ("proposal_decision", {"request_revision": 2, "accepted": 1, "explicit": True}),
    ("proposal", {"request_revision": 1}),
])
def test_confirmacion_o_resultado_obsoleto_no_es_aceptado(field, value):
    state = accepted_state()
    state[field] = value
    assert not contracts.proposal_is_accepted(state)


def test_cambio_invalida_resultados_y_operaciones_sin_mutar_original():
    original = accepted_state()
    before = deepcopy(original)
    patch = contracts.invalidate_request(original)
    revised = {**original, **patch}
    assert original == before
    assert revised["request_revision"] == 3
    assert revised["customer_id"] == 12 and revised["ticket_id"] == 7
    assert revised["intake"] == original["intake"]
    assert revised["requested_items"] == original["requested_items"]
    assert "messages" not in patch  # add_messages no debe duplicar historial.
    assert revised["inventory_results"] == [] and revised["inventory_pending"] is True
    assert revised["quote"] == {} and revised["proposal"] is None
    for key in ("quote_id", "payment_id", "payment_code", "warranty_id", "warranty_code",
                "refund_id", "logistics_record_id", "warranty_claim_id", "claim_code",
                "supplier_id", "purchase_order_id", "inventory_revision", "proposal_decision"):
        assert revised[key] is None
    assert revised["technical_assessment"] == {} and revised["supplier_offers"] == []
    assert not contracts.proposal_is_accepted(revised)
    # Una respuesta tardía de la revisión anterior no reactiva su aceptación.
    revised.update(proposal=original["proposal"], proposal_decision=original["proposal_decision"],
                   inventory_revision=2, inventory_pending=False)
    assert not contracts.proposal_is_accepted(revised)


def test_solicitud_nueva_desvincula_ticket_y_contexto_pero_no_cliente():
    original = accepted_state()
    new = {**original, **contracts.invalidate_request(original, new_request=True)}
    for key in ("ticket_id", "ticket_code", "ticket_status", "intent", "request_type"):
        assert new[key] is None
    assert new["intake"] == {} and new["requested_items"] == []
    assert new["customer_id"] == original["customer_id"]
    assert new["current_agent"] == "soporte"
    assert original["ticket_id"] == 7  # No borra ni cambia registros persistidos.


@pytest.mark.parametrize("revision", [-1, True, "2", None])
def test_version_invalida_se_rechaza(revision):
    with pytest.raises(ValueError, match="Versión"):
        contracts.invalidate_request({"request_revision": revision})


def test_dinero_en_contratos_nuevos_es_decimal():
    for contract, fields in (
        (contracts.IntakeData, ["budget"]),
        (contracts.CatalogItem, ["unit_price"]),
        (contracts.SupplierOffer, ["unit_cost"]),
        (contracts.ProposalLine, ["unit_price", "subtotal"]),
        (contracts.CommercialProposal, ["labor_cost", "parts_cost", "total_amount"]),
        (contracts.PaymentData, ["amount"]), (contracts.RefundData, ["amount"]),
    ):
        hints = get_type_hints(contract)
        assert all(hints[field] is Decimal for field in fields)
