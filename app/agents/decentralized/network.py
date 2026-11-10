"""Patrón Red descentralizada: agentes pares con transferencias validadas.

Usa los mismos agentes de trabajo que el Jerárquico y el Orquestador
(`make_worker_nodes`). Lo propio de este patrón es la coordinación:

- No hay supervisor ni función de enrutamiento central. Cada agente decide a
  qué par transfiere el trabajo y lo hace con `Command(goto=...)`.
- Cada transferencia se valida contra `ALLOWED_HANDOFFS` (quién puede derivar
  a quién) y se registra en `handoffs` con origen, destino y motivo.
- Un límite de transferencias por turno corta cualquier bucle entre pares.
- Cada mensaje del cliente entra por Recepción, el par que conoce los flujos
  pendientes de la conversación (confirmaciones, selecciones, logística).
"""
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.adapters.llm.model_factory import create_model
from app.agents.decentralized.network_state import NetworkState
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
from app.database.repository import ServiceRepository
from app.settings import Settings, load_settings

RECEPTION = "reception_agent"
MAX_HANDOFFS_PER_TURN = 12

# Matriz de transferencias permitidas entre pares. Un destino ausente es un
# error de coordinación, no una ruta alternativa.
ALLOWED_HANDOFFS: dict[str, frozenset[str]] = {
    RECEPTION: frozenset({
        "faq_agent", "out_of_scope_agent", "knowledge_retrieval", "warehouse_agent",
        "warranty_agent", "logistics_agent", "refund_agent",
    }),
    "knowledge_retrieval": frozenset({"technical_support_agent", "software_support_agent"}),
    "technical_support_agent": frozenset({"persist_diagnosis"}),
    "software_support_agent": frozenset({"persist_diagnosis"}),
    "persist_diagnosis": frozenset({"warehouse_agent"}),
    "warehouse_agent": frozenset({"sales_agent"}),
    "sales_agent": frozenset({"billing_agent", "quote_suggestion_response"}),
    "logistics_agent": frozenset({"order_completion_agent"}),
    "faq_agent": frozenset(),
    "out_of_scope_agent": frozenset(),
    "warranty_agent": frozenset(),
    "refund_agent": frozenset(),
    "order_completion_agent": frozenset(),
    "billing_agent": frozenset(),
    "quote_suggestion_response": frozenset(),
}

HANDOFF_REASONS = {
    "faq_agent": "Consulta informativa del negocio",
    "out_of_scope_agent": "Consulta ajena al dominio",
    "knowledge_retrieval": "Recuperar casos técnicos antes de diagnosticar",
    "technical_support_agent": "Evaluar falla física con el contexto recuperado",
    "software_support_agent": "Evaluar falla lógica con el contexto recuperado",
    "persist_diagnosis": "Registrar la evaluación en el ticket del cliente",
    "warehouse_agent": "Verificar stock y precios en el catálogo",
    "sales_agent": "Calcular la cotización con inventario verificado",
    "billing_agent": "Cliente aceptó; registrar cotización y pago pendiente",
    "quote_suggestion_response": "Presentar la propuesta al cliente",
    "warranty_agent": "Consultar o reclamar garantía",
    "logistics_agent": "Registrar modo de entrega",
    "order_completion_agent": "Cerrar la orden tras la logística",
    "refund_agent": "Registrar solicitud de reembolso pendiente",
}


def _reception_decision(state: dict[str, Any]) -> str:
    target = after_supervisor(state)
    if target == "technical_team_supervisor":
        return "knowledge_retrieval"
    if target == "commercial_team_supervisor":
        return "warehouse_agent"
    if target == "operations_team_supervisor":
        return after_operations_supervisor(state)
    return target


def _ends_turn(_state: dict[str, Any]) -> str:
    return END


# Cada par conoce solo su propia regla de derivación.
PEER_DECISIONS: dict[str, Callable[[dict[str, Any]], str]] = {
    RECEPTION: _reception_decision,
    "knowledge_retrieval": after_knowledge_retrieval,
    "technical_support_agent": lambda _state: "persist_diagnosis",
    "software_support_agent": lambda _state: "persist_diagnosis",
    "persist_diagnosis": lambda _state: "warehouse_agent",
    "warehouse_agent": after_inventory,
    "sales_agent": after_sales,
    "logistics_agent": after_logistics,
    **{
        name: _ends_turn
        for name in (
            "faq_agent", "out_of_scope_agent", "warranty_agent", "refund_agent",
            "order_completion_agent", "billing_agent",
            "quote_suggestion_response",
        )
    },
}


def validate_handoff(origin: str, destination: str, handoff_count: int) -> None:
    if origin not in ALLOWED_HANDOFFS or destination not in ALLOWED_HANDOFFS:
        raise ValueError("Agente de transferencia desconocido.")
    if destination not in ALLOWED_HANDOFFS[origin]:
        raise ValueError(f"Transferencia no permitida: {origin} -> {destination}.")
    if handoff_count >= MAX_HANDOFFS_PER_TURN:
        raise ValueError("Se superó el límite de transferencias del turno.")


def _peer(name: str, work: Callable[[dict[str, Any]], dict[str, Any]], *, new_turn: bool = False):
    decide = PEER_DECISIONS[name]

    def run(state: NetworkState) -> Command:
        update = work(state)
        merged = {**state, **update}
        destination = decide(merged)
        history = [] if new_turn else list(state.get("handoffs", []))
        values = {**update, "active_peer": name}
        if destination == END:
            return Command(update={**values, "handoffs": history}, goto=END)
        validate_handoff(name, destination, len(history))
        history.append({
            "origin": name,
            "destination": destination,
            "reason": HANDOFF_REASONS[destination],
        })
        return Command(update={**values, "handoffs": history}, goto=destination)

    run.__name__ = name
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

    graph = StateGraph(NetworkState)
    reception = traced_node(
        RECEPTION, make_customer_care_supervisor(llm, repository), root=True
    )
    graph.add_node(
        RECEPTION,
        _peer(RECEPTION, reception, new_turn=True),
        destinations=tuple(sorted(ALLOWED_HANDOFFS[RECEPTION])),
    )
    for name, node in make_worker_nodes(
        settings=settings, repository=repository, llm=llm, retriever=retriever
    ).items():
        graph.add_node(
            name,
            _peer(name, node),
            destinations=tuple(sorted(ALLOWED_HANDOFFS[name])) or (END,),
        )
    graph.add_edge(START, RECEPTION)
    return graph.compile(checkpointer=InMemorySaver())


def new_thread_id() -> str:
    return str(uuid4())


assert set(ALLOWED_HANDOFFS) == {RECEPTION, *WORKER_NAMES}
assert set(PEER_DECISIONS) == set(ALLOWED_HANDOFFS)
