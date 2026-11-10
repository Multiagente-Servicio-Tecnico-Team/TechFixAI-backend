"""El ticket guarda los repuestos recomendados dentro del diagnóstico."""
import pytest
from langchain_core.messages import HumanMessage

import tests.integration.test_multiagent_graph as multiagent
from app.agents.decentralized.network import build_graph as build_network
from app.agents.jerarquico.graph.builder import build_multiagent_graph
from app.agents.jerarquico.persistence import (
    RECOMMENDED_PARTS_HEADER,
    diagnosis_with_recommended_parts,
    make_persist_diagnosis,
)
from app.agents.jerarquico.schemas import IntakeDecision, TechnicalDiagnosis
from app.agents.orquestador import build_graph as build_orchestrator


def test_without_recommended_parts_only_the_diagnosis_is_saved():
    assert diagnosis_with_recommended_parts("  Revisar el adaptador Wi-Fi.  ", []) == "Revisar el adaptador Wi-Fi."
    assert diagnosis_with_recommended_parts("Revisar.", None) == "Revisar."


def test_recommended_parts_are_listed_after_the_diagnosis():
    text = diagnosis_with_recommended_parts(
        "El almacenamiento podría limitar el rendimiento.",
        [{"search_term": "SSD_1TB", "quantity": 1}, {"search_term": "Pasta térmica", "quantity": 2}],
    )
    assert text == (
        "El almacenamiento podría limitar el rendimiento.\n\n"
        f"{RECOMMENDED_PARTS_HEADER}\n- SSD_1TB × 1\n- Pasta térmica × 2"
    )


def test_persist_diagnosis_writes_combined_text_to_the_ticket():
    class Recorder:
        def update_ticket_diagnosis(self, **values):
            self.values = values

    repository = Recorder()
    make_persist_diagnosis(repository)({
        "ticket_id": 31, "customer_id": 1, "diagnosis_type": "HARDWARE",
        "provisional_diagnosis": "Ventilador obstruido.",
        "required_parts": [{"search_term": "Ventilador HP", "quantity": 1}],
    })
    assert repository.values["ticket_id"] == 31
    assert repository.values["diagnosis"].endswith("- Ventilador HP × 1")


@pytest.mark.parametrize("builder", [build_multiagent_graph, build_orchestrator, build_network],
                         ids=["hierarchical", "orchestrator", "decentralized"])
@pytest.mark.parametrize(
    ("message", "intake", "diagnosis", "expected_parts"),
    [
        (
            "Mi laptop está lenta y demora en abrir aplicaciones.",
            IntakeDecision(route="service", request_type="REPAIR", title="Laptop lenta",
                           failure_description="Demora en abrir aplicaciones."),
            TechnicalDiagnosis(provisional_diagnosis="El almacenamiento podría limitar el rendimiento.",
                               labor_task_type="diagnosis", required_parts=[]),
            ["- SSD_1TB × 1"],
        ),
        (
            "Necesito soporte con mi laptop. No logra conectarse al Wi-Fi desde hoy.",
            IntakeDecision(route="service", request_type="SUPPORT", title="Laptop sin Wi-Fi",
                           failure_description="No logra conectarse al Wi-Fi desde hoy."),
            TechnicalDiagnosis(provisional_diagnosis="Revisar configuración y controlador de red.",
                               labor_task_type="diagnosis", required_parts=[]),
            [],
        ),
    ],
    ids=["with-parts", "ticket-only"],
)
def test_every_pattern_stores_recommended_parts_on_the_ticket(builder, message, intake, diagnosis, expected_parts):
    repository = multiagent.FakeRepository()
    model = multiagent.FakeStructuredModel(
        intake=intake, diagnosis=diagnosis,
        confirmation=multiagent.QuoteConfirmation(decision="unclear"),
    )
    graph = builder(settings=multiagent.make_settings(), repository=repository, model=model)
    graph.invoke({"messages": [HumanMessage(content=message)], "customer_id": 12},
                 config={"configurable": {"thread_id": f"parts-{builder.__module__}-{bool(expected_parts)}"}})

    saved = repository.saved_diagnosis["diagnosis"]
    assert saved.startswith(diagnosis.provisional_diagnosis)
    if expected_parts:
        assert RECOMMENDED_PARTS_HEADER in saved
        assert saved.splitlines()[-len(expected_parts):] == expected_parts
    else:
        assert RECOMMENDED_PARTS_HEADER not in saved
