"""Orquestador y Red descentralizada ejecutan los mismos flujos que el Jerárquico.

Se reutilizan las pruebas de integración del Jerárquico reemplazando solo el
constructor del grafo: los agentes de trabajo son los mismos y solo cambia la
coordinación, así que los resultados de negocio deben coincidir.
"""
import inspect
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END

import tests.integration.test_hierarchical_workflows as workflows
import tests.integration.test_multiagent_graph as multiagent
from app.agents.decentralized.network import (
    ALLOWED_HANDOFFS,
    MAX_HANDOFFS_PER_TURN,
    RECEPTION,
    validate_handoff,
)
from app.agents.decentralized.network import build_graph as build_network_graph
from app.agents.jerarquico.graph.builder import WORKER_NAMES
from app.agents.jerarquico.schemas import IntakeDecision, QuoteConfirmation, TechnicalDiagnosis
from app.agents.orquestador import build_graph as build_orchestrator_graph
from app.agents.orquestador.graph.hub import SUPERVISOR

BUILDERS = {"orchestrator": build_orchestrator_graph, "decentralized": build_network_graph}


class OrchestratorSharedGraphTests(multiagent.MultiagentGraphTests):
    def setUp(self):
        patcher = patch.object(multiagent, "build_multiagent_graph", build_orchestrator_graph)
        patcher.start()
        self.addCleanup(patcher.stop)


class DecentralizedSharedGraphTests(multiagent.MultiagentGraphTests):
    def setUp(self):
        patcher = patch.object(multiagent, "build_multiagent_graph", build_network_graph)
        patcher.start()
        self.addCleanup(patcher.stop)


_GRAPH_WORKFLOWS = [
    name
    for name, function in vars(workflows).items()
    if name.startswith("test_")
    and callable(function)
    and "build_multiagent_graph" in inspect.getsource(function)
]


@pytest.mark.parametrize("pattern_id", sorted(BUILDERS))
@pytest.mark.parametrize("test_name", _GRAPH_WORKFLOWS)
def test_hierarchical_workflow_runs_identically(test_name, pattern_id, monkeypatch):
    monkeypatch.setattr(workflows, "build_multiagent_graph", BUILDERS[pattern_id])
    getattr(workflows, test_name)()


def _service_model():
    return multiagent.FakeStructuredModel(
        intake=IntakeDecision(
            route="service",
            request_type="REPAIR",
            title="Laptop se apaga",
            failure_description="La laptop se apaga por temperatura.",
        ),
        diagnosis=TechnicalDiagnosis(
            provisional_diagnosis="Obstrucción del sistema de disipación.",
            labor_task_type="diagnosis",
        ),
        confirmation=QuoteConfirmation(decision="unclear"),
    )


def _graph(pattern_id, model=None):
    return BUILDERS[pattern_id](
        settings=workflows.make_settings(),
        repository=multiagent.FakeRepository(),
        model=model or object(),
    )


# --- Orquestador: estrella con supervisor único -------------------------------

def test_orchestrator_workers_return_control_to_the_single_supervisor():
    graph = _graph("orchestrator").get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}
    for worker in WORKER_NAMES:
        assert (worker, SUPERVISOR) in edges
        assert not any(source == worker and target in WORKER_NAMES for source, target in edges)
    assert not any("team_supervisor" in node for node in graph.nodes)


def test_orchestrator_supervisor_mediates_between_each_service_step():
    visited = []
    for chunk in _graph("orchestrator", _service_model()).stream(
        {"messages": [HumanMessage(content="Mi laptop se apaga por temperatura")], "customer_id": 12},
        config={"configurable": {"thread_id": "orchestrator-steps"}},
        stream_mode="updates",
    ):
        visited.extend(chunk)
    workers = [node for node in visited if node != SUPERVISOR]
    assert workers[:2] == ["knowledge_retrieval", "technical_support_agent"]
    for previous, current in zip(visited, visited[1:]):
        assert SUPERVISOR in {previous, current}


# --- Red descentralizada: pares con transferencias validadas -------------------

def test_network_has_no_supervisor_and_only_declared_peer_handoffs():
    graph = _graph("decentralized").get_graph()
    assert SUPERVISOR not in graph.nodes
    assert not any("supervisor" in node for node in graph.nodes)
    for edge in graph.edges:
        if edge.source in ALLOWED_HANDOFFS and edge.target != END:
            assert edge.target in ALLOWED_HANDOFFS[edge.source]


def test_network_peers_hand_off_directly_and_record_each_transfer():
    result = _graph("decentralized", _service_model()).invoke(
        {"messages": [HumanMessage(content="Mi laptop se apaga por temperatura")], "customer_id": 12},
        config={"configurable": {"thread_id": "network-steps"}},
    )
    route = [(h["origin"], h["destination"]) for h in result["handoffs"]]
    assert route == [
        (RECEPTION, "knowledge_retrieval"),
        ("knowledge_retrieval", "technical_support_agent"),
        ("technical_support_agent", "persist_diagnosis"),
        ("persist_diagnosis", "warehouse_agent"),
        ("warehouse_agent", "sales_agent"),
        ("sales_agent", "quote_suggestion_response"),
    ]
    assert all(h["reason"] for h in result["handoffs"])
    assert result["active_peer"] == "quote_suggestion_response"
    assert result["outcome"] == "awaiting_confirmation"


def test_network_handoff_history_restarts_on_each_customer_turn():
    graph = _graph("decentralized", _service_model())
    config = {"configurable": {"thread_id": "network-turns"}}
    graph.invoke({"messages": [HumanMessage(content="Mi laptop se apaga por temperatura")], "customer_id": 12}, config=config)
    second = graph.invoke({"messages": [HumanMessage(content="no sé")], "customer_id": 12}, config=config)
    assert all(h["origin"] != "knowledge_retrieval" for h in second["handoffs"])


@pytest.mark.parametrize(
    ("origin", "destination"),
    [
        ("faq_agent", "billing_agent"),
        ("reception_agent", "billing_agent"),
        ("warehouse_agent", "reception_agent"),
        ("unknown", "faq_agent"),
    ],
)
def test_network_rejects_undeclared_handoffs(origin, destination):
    with pytest.raises(ValueError):
        validate_handoff(origin, destination, 0)


def test_network_limits_handoffs_per_turn():
    with pytest.raises(ValueError, match="límite"):
        validate_handoff(RECEPTION, "faq_agent", MAX_HANDOFFS_PER_TURN)
