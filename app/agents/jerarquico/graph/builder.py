from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.jerarquico.knowledge_retrieval import (
    make_knowledge_retrieval_agent,
)
from app.agents.jerarquico.agents.billing import make_billing_agent
from app.agents.jerarquico.agents.faq import MarkdownFaqRetriever, make_faq_agent
from app.agents.jerarquico.agents.out_of_scope import make_out_of_scope_agent
from app.agents.jerarquico.agents.logistics import make_logistics_agent
from app.agents.refund_requests import make_refund_agent
from app.agents.jerarquico.agents.teams import make_team_supervisor
from app.agents.jerarquico.agents.warranty import (
    make_order_completion_agent,
    make_warranty_agent,
)
from app.agents.jerarquico.persistence import make_persist_diagnosis
from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever
from app.agents.jerarquico.sales import make_sales_agent, quote_suggestion_response
from app.agents.jerarquico.supervisor import make_customer_care_supervisor
from app.agents.jerarquico.technical_support import make_technical_support_agent
from app.agents.jerarquico.trace import traced_node, traced_tool
from app.agents.jerarquico.warehouse import make_warehouse_agent
from app.database.repository import ServiceRepository
from app.adapters.llm.model_factory import create_model
from app.agents.jerarquico.graph.routing import (
    after_inventory,
    after_logistics,
    after_knowledge_retrieval,
    after_operations_supervisor,
    after_sales,
    after_supervisor,
    after_technical_supervisor,
)
from app.agents.jerarquico.graph.state import ServiceState
from app.settings import Settings, load_settings


WORKER_NAMES = (
    "faq_agent",
    "out_of_scope_agent",
    "warranty_agent",
    "refund_agent",
    "order_completion_agent",
    "logistics_agent",
    "billing_agent",
    "knowledge_retrieval",
    "technical_support_agent",
    "software_support_agent",
    "warehouse_agent",
    "sales_agent",
    "quote_suggestion_response",
    "persist_diagnosis",
)


def make_worker_nodes(
    *,
    settings: Settings,
    repository: ServiceRepository,
    llm: Any,
    retriever: MarkdownKnowledgeRetriever,
    direct_sales_quotes: Any | None = None,
) -> dict[str, Any]:
    """Agentes de trabajo CUSTOMER compartidos por los tres patrones.

    Los patrones solo difieren en cómo coordinan estos nodos; las reglas de
    negocio, RAG, herramientas y persistencia son las mismas.
    """
    faq_retriever = MarkdownFaqRetriever()
    nodes = {
        "faq_agent": make_faq_agent(llm, faq_retriever),
        "out_of_scope_agent": make_out_of_scope_agent(llm),
        "warranty_agent": make_warranty_agent(repository),
        "refund_agent": make_refund_agent(repository, trace_tool=traced_tool),
        "order_completion_agent": make_order_completion_agent(repository),
        "logistics_agent": make_logistics_agent(llm, repository),
        "billing_agent": make_billing_agent(repository, direct_sales_quotes),
        "knowledge_retrieval": make_knowledge_retrieval_agent(retriever),
        "technical_support_agent": make_technical_support_agent(llm, mode="hardware"),
        "software_support_agent": make_technical_support_agent(llm, mode="software"),
        "warehouse_agent": make_warehouse_agent(
            repository,
            pc_build_labor_cost=settings.labor_price_for("pc_build"),
        ),
        "sales_agent": make_sales_agent(settings, direct_sales_quotes),
        "quote_suggestion_response": quote_suggestion_response,
        "persist_diagnosis": make_persist_diagnosis(repository),
    }
    assert tuple(nodes) == WORKER_NAMES
    return {name: traced_node(name, node) for name, node in nodes.items()}


def build_multiagent_graph(
    *,
    settings: Settings | None = None,
    repository: ServiceRepository | None = None,
    model: Any | None = None,
    retriever: MarkdownKnowledgeRetriever | None = None,
    direct_sales_quotes: Any | None = None,
):
    settings = settings or load_settings()
    settings.require_chat_configuration()
    repository = repository or ServiceRepository()
    retriever = retriever or MarkdownKnowledgeRetriever()
    llm = model or create_model(settings)

    graph = StateGraph(ServiceState)
    graph.add_node(
        "customer_care_supervisor",
        traced_node(
            "customer_care_supervisor",
            make_customer_care_supervisor(llm, repository),
            root=True,
        ),
    )
    for team in ("commercial", "technical", "operations"):
        graph.add_node(
            f"{team}_team_supervisor",
            traced_node(f"{team}_team_supervisor", make_team_supervisor(team)),
        )
    for name, node in make_worker_nodes(
        settings=settings, repository=repository, llm=llm, retriever=retriever,
        direct_sales_quotes=direct_sales_quotes,
    ).items():
        graph.add_node(name, node)

    graph.add_edge(START, "customer_care_supervisor")
    graph.add_conditional_edges(
        "customer_care_supervisor",
        after_supervisor,
        {
            "technical_team_supervisor": "technical_team_supervisor",
            "commercial_team_supervisor": "commercial_team_supervisor",
            "operations_team_supervisor": "operations_team_supervisor",
            "refund_agent": "refund_agent",
            "faq_agent": "faq_agent",
            "out_of_scope_agent": "out_of_scope_agent",
            "knowledge_retrieval": "knowledge_retrieval",
            "warehouse_agent": "warehouse_agent",
            END: END,
        },
    )
    graph.add_edge("commercial_team_supervisor", "warehouse_agent")
    graph.add_conditional_edges(
        "technical_team_supervisor",
        after_technical_supervisor,
        {
            "knowledge_retrieval": "knowledge_retrieval",
        },
    )
    graph.add_conditional_edges(
        "operations_team_supervisor",
        after_operations_supervisor,
        {
            "warranty_agent": "warranty_agent",
            "logistics_agent": "logistics_agent",
            END: END,
        },
    )
    graph.add_edge("faq_agent", END)
    graph.add_edge("out_of_scope_agent", END)
    graph.add_edge("warranty_agent", END)
    graph.add_edge("refund_agent", END)
    graph.add_conditional_edges(
        "logistics_agent",
        after_logistics,
        {
            "order_completion_agent": "order_completion_agent",
            END: END,
        },
    )
    graph.add_edge("order_completion_agent", END)
    graph.add_edge("billing_agent", END)
    graph.add_conditional_edges(
        "knowledge_retrieval",
        after_knowledge_retrieval,
        {
            "technical_support_agent": "technical_support_agent",
            "software_support_agent": "software_support_agent",
        },
    )
    graph.add_edge("technical_support_agent", "persist_diagnosis")
    graph.add_edge("software_support_agent", "persist_diagnosis")
    graph.add_edge("persist_diagnosis", "warehouse_agent")
    graph.add_conditional_edges(
        "warehouse_agent",
        after_inventory,
        {
            "sales_agent": "sales_agent",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "sales_agent",
        after_sales,
        {
            "billing_agent": "billing_agent",
            "quote_suggestion_response": "quote_suggestion_response",
        },
    )
    graph.add_edge("quote_suggestion_response", END)

    return graph.compile(checkpointer=InMemorySaver())
