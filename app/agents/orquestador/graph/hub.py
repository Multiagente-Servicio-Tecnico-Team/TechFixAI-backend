"""Patrón Orquestador / supervisor: topología en estrella.

Usa los mismos agentes CUSTOMER que los patrones Jerárquico y Descentralizado
(`make_worker_nodes`): FAQ, fuera de dominio, soporte de hardware/software, RAG
técnico, almacén, ventas, facturación, logística, garantía y reembolsos. Las
compras a proveedores quedan en las capacidades ADMIN. Lo propio de este patrón
es la coordinación:

- Jerárquico: supervisor principal -> supervisores de equipo -> cadenas de
  agentes que se pasan el trabajo entre sí.
- Orquestador: un único supervisor clasifica la solicitud y, después de cada
  agente, recibe el control de vuelta y decide el siguiente paso. Ningún agente
  llama directamente a otro.
"""
from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.adapters.llm.model_factory import create_model
from app.agents.jerarquico.graph.builder import WORKER_NAMES, make_worker_nodes
from app.agents.jerarquico.graph.routing import (
    after_inventory,
    after_knowledge_retrieval,
    after_logistics,
    after_operations_supervisor,
    after_sales,
    after_supervisor,
)
from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever
from app.agents.jerarquico.supervisor import make_customer_care_supervisor
from app.agents.jerarquico.trace import traced_node
from app.agents.orquestador.graph.orchestrator_state import OrchestratorState
from app.database.repository import ServiceRepository
from app.settings import Settings, load_settings

SUPERVISOR = "orchestrator_supervisor"
INTAKE = "intake"

# Agentes que terminan el turno al devolver el control.
_TERMINAL_AGENTS = {
    "faq_agent",
    "out_of_scope_agent",
    "warranty_agent",
    "refund_agent",
    "order_completion_agent",
    "billing_agent",
    "quote_suggestion_response",
}


def _human_turns(state: OrchestratorState) -> int:
    return sum(isinstance(message, HumanMessage) for message in state.get("messages", []))


def _route_after_intake(state: OrchestratorState) -> str:
    """Misma decisión del supervisor jerárquico, sin la capa de equipos."""
    target = after_supervisor(state)
    if target == "technical_team_supervisor":
        return "knowledge_retrieval"
    if target == "commercial_team_supervisor":
        return "warehouse_agent"
    if target == "operations_team_supervisor":
        return after_operations_supervisor(state)
    return target


def next_step(state: OrchestratorState) -> str:
    """Decisión central del supervisor tras la clasificación o tras cada agente."""
    last = state.get("last_agent", INTAKE)
    if last == INTAKE:
        return _route_after_intake(state)
    if last in _TERMINAL_AGENTS:
        return END
    if last == "knowledge_retrieval":
        return after_knowledge_retrieval(state)
    if last in {"technical_support_agent", "software_support_agent"}:
        return "persist_diagnosis"
    if last == "persist_diagnosis":
        return "warehouse_agent"
    if last == "warehouse_agent":
        return after_inventory(state)
    if last == "sales_agent":
        return after_sales(state)
    if last == "logistics_agent":
        return after_logistics(state)
    raise ValueError("El supervisor recibió el control de un agente desconocido.")


def make_orchestrator_supervisor(llm: Any, repository: ServiceRepository):
    intake = traced_node(
        SUPERVISOR,
        make_customer_care_supervisor(llm, repository),
        root=True,
    )

    def orchestrator_supervisor(state: OrchestratorState) -> dict[str, Any]:
        turns = _human_turns(state)
        if state.get("orchestrator_turn") != turns:
            # Mensaje nuevo del cliente: clasificar intención y flujo pendiente.
            return {**intake(state), "last_agent": INTAKE, "orchestrator_turn": turns}
        # Un agente devolvió el control; la decisión la toma `next_step`.
        return {}

    return orchestrator_supervisor


def _returning_to_supervisor(name: str, node: Any):
    def run(state: OrchestratorState) -> dict[str, Any]:
        return {**node(state), "last_agent": name}

    return run


def build_graph(
    *,
    settings: Settings | None = None,
    repository: ServiceRepository | None = None,
    model: Any | None = None,
    retriever: MarkdownKnowledgeRetriever | None = None,
):
    settings = settings or load_settings()
    settings.require_chat_configuration()
    repository = repository or ServiceRepository()
    retriever = retriever or MarkdownKnowledgeRetriever()
    llm = model or create_model(settings)

    graph = StateGraph(OrchestratorState)
    graph.add_node(SUPERVISOR, make_orchestrator_supervisor(llm, repository))
    for name, node in make_worker_nodes(
        settings=settings, repository=repository, llm=llm, retriever=retriever
    ).items():
        graph.add_node(name, _returning_to_supervisor(name, node))
        graph.add_edge(name, SUPERVISOR)

    graph.add_edge(START, SUPERVISOR)
    graph.add_conditional_edges(
        SUPERVISOR,
        next_step,
        {**{name: name for name in WORKER_NAMES}, END: END},
    )
    return graph.compile(checkpointer=InMemorySaver())


def new_thread_id() -> str:
    return str(uuid4())
