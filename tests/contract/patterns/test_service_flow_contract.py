from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.application.logistics import record_customer_logistics_preference
from app.application.pc_builds import available_pc_builds, replace_pc_build_component
from app.application.quotes import interpret_quote_decision
from app.application.quotes import accept_quoted_draft
from app.agents.jerarquico.schemas import IntakeDecision
from app.agents.jerarquico.supervisor import make_customer_care_supervisor
from app.agents.orquestador.graph.state import IntakeResult
from langchain_core.messages import AIMessage, HumanMessage
from app.application.warranties import (
    lookup_customer_warranty,
    register_customer_warranty_claim,
)


class ServiceRepository:
    def __init__(self):
        self.writes = []

    def find_warranty(self, code):
        if code != "WAR-OWNED":
            return None
        return {
            "id": 4, "customer_id": 41, "warranty_code": code,
            "status": "ACTIVE", "not_expired": True,
            "end_date": date.today() + timedelta(days=30),
            "item_or_service_name": "Equipo",
        }

    def create_warranty_claim(self, **values):
        self.writes.append(("claim", values))

    def create_logistics_record(self, **values):
        self.writes.append(("logistics", values))
        return 12

    def find_spare_part_by_code(self, code):
        return {
            "id": 1, "code": code, "name": f"Parte {code}",
            "category": "CPU", "unit_price": Decimal("200"),
            "current_stock": 2,
        }

    def find_customer(self, _email):
        return {"id": 41}


class ClarificationModel:
    def with_structured_output(self, schema, **_kwargs):
        self.schema = schema
        return self

    def invoke(self, _messages):
        if self.schema is IntakeDecision:
            return IntakeDecision(route="clarification", clarification_question="¿Qué modelo de equipo tienes?")
        if self.schema is IntakeResult:
            return IntakeResult(
                category="Soporte técnico", product="", symptoms="",
                needs_clarification=True,
                clarification_question="¿Qué modelo de equipo tienes?",
            )
        raise AssertionError("Unexpected schema")


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_owned_warranty_claim_and_logistics_have_equivalent_policy(pattern_id):
    repository = ServiceRepository()
    warranty = lookup_customer_warranty(
        repository, customer_id=41, warranty_code="WAR-OWNED"
    )
    assert warranty["status"] == "ACTIVE"

    claim = register_customer_warranty_claim(
        repository, customer_id=41, ticket_id=9, warranty_code="WAR-OWNED",
        reason=f"Falla reportada en {pattern_id}", claim_code=f"CLM-{pattern_id}",
    )
    assert claim["status"] == "IN_REVIEW"
    assert claim["ticket_status"] == "WARRANTY_IN_REVIEW"

    record_id = record_customer_logistics_preference(
        repository, customer_id=41, ticket_id=9, mode="PHYSICAL_STORE"
    )
    assert record_id == 12
    assert [operation for operation, _ in repository.writes] == ["claim", "logistics"]
    assert repository.writes[1][1]["customer_id"] == 41


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
@pytest.mark.parametrize("customer_id,code", [(42, "WAR-OWNED"), (41, "WAR-OTHER")])
def test_unowned_or_unknown_warranty_claim_has_zero_writes(pattern_id, customer_id, code):
    repository = ServiceRepository()
    assert lookup_customer_warranty(
        repository, customer_id=customer_id, warranty_code=code
    ) is None
    with pytest.raises(LookupError):
        register_customer_warranty_claim(
            repository, customer_id=customer_id, ticket_id=9,
            warranty_code=code, reason="No funciona",
        )
    assert repository.writes == []


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_logistics_requires_courier_details_and_never_claims_delivery(pattern_id):
    repository = ServiceRepository()
    with pytest.raises(ValueError):
        record_customer_logistics_preference(
            repository, customer_id=41, ticket_id=9, mode="COURIER_SHIPMENT"
        )
    assert repository.writes == []
    record_customer_logistics_preference(
        repository, customer_id=41, ticket_id=9, mode="COURIER_SHIPMENT",
        courier_company="Courier Uno", shipping_address="Calle 1",
    )
    assert repository.writes[0][1]["mode"] == "COURIER_SHIPMENT"


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_pc_build_is_catalog_priced_and_modification_does_not_reserve(pattern_id):
    repository = ServiceRepository()
    profiles = ({
        "identifier": "office", "title": "Oficina", "uses": ("oficina",),
        "components": (("CPU", "CPU-OFFICE"),),
        "compatibility_notes": "Validar compatibilidad física.",
    },)
    options = available_pc_builds(
        repository, intended_use="oficina", labor_cost=Decimal("50"),
        budget_max=Decimal("300"), profiles=profiles,
    )
    assert options[0]["total"] == Decimal("250")
    assert options[0]["within_budget"] is True
    assert repository.writes == []


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_pc_build_component_change_uses_same_category_and_live_catalog_rules(pattern_id):
    repository = ServiceRepository()
    parts = [{"code": "CPU-OLD", "name": "CPU anterior", "category": "CPU",
              "quantity": 1, "unit_price": Decimal("50")}]
    revised = replace_pc_build_component(
        repository, current_parts=parts, category="CPU", replacement_code="CPU-NEW"
    )
    assert revised[0]["code"] == "CPU-NEW"
    assert revised[0]["unit_price"] == Decimal("200")
    assert repository.writes == []


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
@pytest.mark.parametrize("answer,expected", [("Sí, confirmo", "ACCEPT"), ("No, rechazo", "REJECT")])
def test_quote_confirmation_semantics_match_all_patterns(pattern_id, answer, expected):
    assert interpret_quote_decision(answer) == expected


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_payment_remains_pending_after_quote_acceptance(pattern_id):
    class Writer:
        calls = []
        def accept_ticket_quote(self, **values):
            self.calls.append(values)
            return {"payment_status": "PENDING", "payment_code": "PAY-CONTRACT"}

    writer = Writer()
    draft = {
        "ticket_id": 9, "quote_type": "DIRECT_SALE", "labor_task_type": "sale",
        "labor_cost": Decimal("0"), "parts_cost": Decimal("25"),
        "total_amount": Decimal("25"),
        "parts": [{"code": "ITEM-1", "quantity": 1,
                   "unit_price": Decimal("25"), "subtotal": Decimal("25")}],
    }
    result = accept_quoted_draft(
        writer=writer, customer_id=41, ticket_id=9, quote_type="DIRECT_SALE",
        draft=draft, observations="Venta directa", payment_code="PAY-CONTRACT",
    )
    assert result["payment_status"] == "PENDING"
    assert writer.calls[0]["customer_id"] == 41
    assert writer.calls[0]["total_amount"] == Decimal("25.00")


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_clarification_and_support_intake_are_non_persisting(pattern_id, monkeypatch):
    repository = ServiceRepository()
    messages = [HumanMessage(content="No recuerdo el modelo del equipo")]
    if pattern_id == "hierarchical":
        result = make_customer_care_supervisor(ClarificationModel(), repository)(
            {"messages": messages, "customer_id": 41}
        )
        assert result["route"] == "clarification"
    elif pattern_id == "orchestrator":
        import app.agents.orquestador.agentes.atencion as atencion
        monkeypatch.setattr(atencion, "create_chat_model", lambda: ClarificationModel())
        result = atencion.atencion_node({"messages": messages, "user_id": 41})
        assert result["awaiting_clarification"] is True
    else:
        import app.agents.decentralized.support as soporte
        class SupportModel:
            def invoke(self, _messages):
                return AIMessage(content="¿Qué modelo de equipo tienes?")
        monkeypatch.setattr(soporte, "llm", SupportModel())
        result = soporte.support_node({"messages": messages, "turn_start_index": 0})
        assert not result["messages"][0].tool_calls
    assert repository.writes == []
