from langchain_core.messages import HumanMessage

from app.agents.orquestador.agentes.atencion import atencion_node


def test_ticket_lookup_code_routes_without_llm():
    result = atencion_node({
        "messages": [HumanMessage(content="¿Cuál es el estado del ticket TCK-ABC123?")]
    })

    assert result == {
        "ticket_code": "TCK-ABC123",
        "ticket_lookup_pending": True,
    }
