from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.jerarquico.knowledge_retrieval import (
    make_knowledge_retrieval_agent,
)
from app.agents.jerarquico.agents.billing import make_billing_agent
from app.agents.jerarquico.agents.faq import MarkdownFaqRetriever, make_faq_agent
from app.agents.jerarquico.agents.logistics import make_logistics_agent
from app.agents.refund_requests import make_refund_agent
from app.agents.jerarquico.agents.procurement import purchasing_agent
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


def build_multiagent_graph(
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
    faq_retriever = MarkdownFaqRetriever()
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
    graph.add_node(
        "commercial_team_supervisor",
        traced_node(
            "commercial_team_supervisor",
            make_team_supervisor("commercial"),
        ),
    )
    graph.add_node(
        "technical_team_supervisor",
        traced_node(
            "technical_team_supervisor",
            make_team_supervisor("technical"),
        ),
    )
    graph.add_node(
        "operations_team_supervisor",
        traced_node(
            "operations_team_supervisor",
            make_team_supervisor("operations"),
        ),
    )
    graph.add_node(
        "faq_agent",
        traced_node("faq_agent", make_faq_agent(llm, faq_retriever)),
    )
    graph.add_node(
        "warranty_agent",
        traced_node("warranty_agent", make_warranty_agent(repository)),
    )
    graph.add_node(
        "refund_agent",
        traced_node("refund_agent", make_refund_agent(repository, trace_tool=traced_tool)),
    )
    graph.add_node(
        "order_completion_agent",
        traced_node(
            "order_completion_agent",
            make_order_completion_agent(repository),
        ),
    )
    graph.add_node(
        "logistics_agent",
        traced_node("logistics_agent", make_logistics_agent(llm, repository)),
    )
    graph.add_node(
        "billing_agent",
        traced_node("billing_agent", make_billing_agent(repository)),
    )
    graph.add_node(
        "purchasing_agent",
        traced_node("purchasing_agent", purchasing_agent),
    )
    graph.add_node(
        "knowledge_retrieval",
        traced_node(
            "knowledge_retrieval",
            make_knowledge_retrieval_agent(retriever),
        ),
    )
    graph.add_node(
        "technical_support_agent",
        traced_node(
            "technical_support_agent",
            make_technical_support_agent(llm, mode="hardware"),
        ),
    )
    graph.add_node(
        "software_support_agent",
        traced_node(
            "software_support_agent",
            make_technical_support_agent(llm, mode="software"),
        ),
    )
    graph.add_node(
        "warehouse_agent",
        traced_node(
            "warehouse_agent",
            make_warehouse_agent(
                repository,
                pc_build_labor_cost=settings.labor_price_for("pc_build"),
            ),
        ),
    )
    graph.add_node(
        "sales_agent",
        traced_node("sales_agent", make_sales_agent(settings)),
    )
    graph.add_node(
        "quote_suggestion_response",
        traced_node("quote_suggestion_response", quote_suggestion_response),
    )
    graph.add_node(
        "persist_diagnosis",
        traced_node(
            "persist_diagnosis",
            make_persist_diagnosis(repository),
        ),
    )

    graph.add_edge(START, "customer_care_supervisor")
    graph.add_conditional_edges(
        "customer_care_supervisor",
        after_supervisor,
        {
            "technical_team_supervisor": "technical_team_supervisor",
            "commercial_team_supervisor": "commercial_team_supervisor",
            "operations_team_supervisor": "operations_team_supervisor",
            "refund_agent": "refund_agent",
            "purchasing_agent": "purchasing_agent",
            "faq_agent": "faq_agent",
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
    graph.add_edge("purchasing_agent", END)
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
            "purchasing_agent": "purchasing_agent",
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
