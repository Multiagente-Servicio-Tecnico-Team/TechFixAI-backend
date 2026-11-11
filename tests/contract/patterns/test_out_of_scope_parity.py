"""Paridad del guard de dominio: los tres patrones rechazan consultas ajenas.

Cada topología enruta a su propio nodo de rechazo (ruta del supervisor
jerárquico, supervisor del Orquestador, handoff entre pares en Descentralizado);
el resultado normalizado es el mismo: negativa sin dato factual y sin escrituras.
"""
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.domain_guard import DomainVerdict

OFF_TOPIC = "¿En qué año fue la declaración de independencia?"
REFUSAL = "Lo siento, solo puedo ayudarte con temas de TechFix, como reparar o cotizar tu equipo."


class OffTopicModel:
    """Clasifica todo como fuera de dominio; falla ante cualquier otro uso estructurado."""

    def __init__(self):
        self.structured = []
        self.free_calls = 0

    def with_structured_output(self, schema, **_kwargs):
        self.structured.append(schema)
        if schema is not DomainVerdict:
            raise AssertionError(f"El flujo de dominio no debe ejecutarse: {schema}")
        return self._Structured()

    class _Structured:
        def invoke(self, _messages):
            return DomainVerdict(in_domain=False, reason="historia")

    def bind_tools(self, *_args, **_kwargs):
        return self

    def invoke(self, _messages):
        self.free_calls += 1
        return AIMessage(content=REFUSAL)


class NoWriteRepository:
    def __getattr__(self, name):
        raise AssertionError(f"Acceso al repositorio no permitido: {name}")


def _final_text(result):
    return next(
        m.content for m in reversed(result["messages"])
        if isinstance(m, AIMessage) and m.content
    )


def _run(pattern_id, model, monkeypatch, pattern_settings):
    messages = [HumanMessage(content=OFF_TOPIC)]
    if pattern_id == "hierarchical":
        from app.agents.jerarquico.graph.builder import build_multiagent_graph

        graph = build_multiagent_graph(
            settings=pattern_settings, repository=NoWriteRepository(), model=model
        )
        result = graph.invoke(
            {"messages": messages, "customer_id": 41, "customer_email": "c@example.com"},
            config={"configurable": {"thread_id": "oos-h"}},
        )
        assert result["outcome"] == "out_of_scope"
        return result
    if pattern_id == "orchestrator":
        from app.agents.orquestador import build_graph

        graph = build_graph(settings=pattern_settings, repository=NoWriteRepository(), model=model)
        result = graph.invoke(
            {"messages": messages, "customer_id": 41},
            config={"configurable": {"thread_id": "oos-o"}},
        )
        assert result["outcome"] == "out_of_scope"
        assert result["last_agent"] == "out_of_scope_agent"
        return result
    from app.agents.decentralized.network import build_graph as build_network

    graph = build_network(settings=pattern_settings, repository=NoWriteRepository(), model=model)
    result = graph.invoke(
        {"messages": messages, "customer_id": 41},
        config={"configurable": {"thread_id": "oos-d"}},
    )
    assert result["outcome"] == "out_of_scope"
    assert result["active_peer"] == "out_of_scope_agent"
    assert [(h["origin"], h["destination"]) for h in result["handoffs"]] == [
        ("reception_agent", "out_of_scope_agent")
    ]
    return result


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_off_topic_question_is_refused_in_every_pattern(pattern_id, monkeypatch, pattern_settings):
    model = OffTopicModel()
    result = _run(pattern_id, model, monkeypatch, pattern_settings)
    reply = _final_text(result)
    assert reply == REFUSAL
    assert "1776" not in reply and "1821" not in reply
    assert model.structured == [DomainVerdict]
