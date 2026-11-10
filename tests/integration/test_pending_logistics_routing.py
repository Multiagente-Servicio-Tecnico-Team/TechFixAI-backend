"""Una preferencia de entrega pendiente no debe secuestrar solicitudes nuevas."""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

import tests.integration.test_multiagent_graph as multiagent
from app.agents.jerarquico.schemas import IntakeDecision, QuoteConfirmation, TechnicalDiagnosis
from app.agents.jerarquico.supervisor import make_customer_care_supervisor


def _supervisor():
    model = multiagent.FakeStructuredModel(
        intake=IntakeDecision(
            route="service",
            request_type="SUPPORT",
            title="Laptop sin Wi-Fi",
            failure_description="No logra conectarse al Wi-Fi desde hoy.",
        ),
        diagnosis=TechnicalDiagnosis(provisional_diagnosis="Revisar adaptador.", labor_task_type="diagnosis"),
        confirmation=QuoteConfirmation(decision="unclear"),
    )
    return make_customer_care_supervisor(model, multiagent.FakeRepository())


def _state(text):
    return {
        "customer_id": 12,
        "awaiting_logistics": True,
        "logistics_ticket_id": 5,
        "messages": [
            AIMessage(content="¿Prefieres retiro presencial en tienda o envío por courier?"),
            HumanMessage(content=text),
        ],
    }


def test_new_support_request_is_not_routed_to_pending_logistics():
    result = _supervisor()(_state("Necesito soporte con mi laptop . No logra conectarse al Wi-Fi desde hoy."))
    assert result["route"] == "service"
    assert result["request_type"] == "SUPPORT"


@pytest.mark.parametrize(
    "answer",
    ["Retiro en tienda", "Envío por courier Olva a Av. Arequipa 123", "Prefiero recogerlo"],
)
def test_delivery_answers_still_reach_pending_logistics(answer):
    assert _supervisor()(_state(answer)) == {"route": "logistics"}


def test_nullable_reference_parameters_are_typed_for_postgres():
    # pg8000 envía None sin tipo; `:param IS NOT NULL` sin CAST produce SQLSTATE 42P18.
    import inspect
    import re

    from app.database import repository

    source = inspect.getsource(repository)
    assert not re.search(r"\(:(ticket_id|sales_order_id) IS NOT NULL", source)
