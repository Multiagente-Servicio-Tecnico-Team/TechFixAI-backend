import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.domain_guard import (
    OUT_OF_SCOPE_FALLBACK,
    DomainVerdict,
    check_domain,
    out_of_scope_reply,
    rule_verdict,
)


class GuardModel:
    """Doble del LLM: veredicto estructurado configurable y respuesta libre."""

    def __init__(self, in_domain=False, reply="Solo puedo ayudarte con temas de TechFix."):
        self.in_domain = in_domain
        self.reply = reply
        self.structured_calls = 0
        self.free_calls = 0

    def with_structured_output(self, schema, **_kwargs):
        assert schema is DomainVerdict
        model = self

        class _Structured:
            def invoke(self, _messages):
                model.structured_calls += 1
                return DomainVerdict(in_domain=model.in_domain, reason="test")

        return _Structured()

    def invoke(self, _messages):
        self.free_calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return AIMessage(content=self.reply)


@pytest.mark.parametrize(
    "text",
    [
        "Mi laptop no enciende",
        "Quiero comprar una memoria RAM de 16GB",
        "¿Cuál es su horario de atención?",
        "Estado de mi ticket TCK-AB12CD",
        "Quiero armar una PC gamer",
        "Necesito un reembolso",
        "Hola",
        "Gracias",
    ],
)
def test_business_messages_are_accepted_by_rules_without_model(text):
    model = GuardModel(in_domain=False)
    check = check_domain(model, [HumanMessage(content=text)])
    assert check.in_domain is True
    assert check.source == "rules"
    assert model.structured_calls == 0


def test_short_answer_to_assistant_question_is_follow_up():
    messages = [
        HumanMessage(content="Mi pc va lenta"),
        AIMessage(content="¿En qué aplicación ocurre?"),
        HumanMessage(content="en el navegador"),
    ]
    assert rule_verdict(messages) is True


@pytest.mark.parametrize(
    "text",
    [
        "¿En qué año fue la declaración de independencia?",
        "¿Qué equipo ganó el último mundial?",
        "¿Cuánto es la raíz cuadrada de 144?",
    ],
)
def test_unknown_topics_are_decided_by_the_model(text):
    model = GuardModel(in_domain=False)
    check = check_domain(model, [HumanMessage(content=text)])
    assert check.in_domain is False
    assert check.source == "llm"
    assert model.structured_calls == 1


def test_classifier_failure_fails_open():
    class Broken:
        def with_structured_output(self, *_args, **_kwargs):
            raise RuntimeError("provider down")

    check = check_domain(Broken(), [HumanMessage(content="¿Quién pintó la Mona Lisa?")])
    assert check.in_domain is True
    assert check.source == "fallback"


def test_invalid_verdict_fails_open():
    class Weird:
        def with_structured_output(self, *_args, **_kwargs):
            return self

        def invoke(self, _messages):
            return AIMessage(content="no es json")

    check = check_domain(Weird(), [HumanMessage(content="¿Quién pintó la Mona Lisa?")])
    assert check.in_domain is True


def test_reply_is_drafted_by_model():
    reply = out_of_scope_reply(GuardModel(reply="No puedo ayudarte con eso, pero sí con tu PC."), "x")
    assert reply == "No puedo ayudarte con eso, pero sí con tu PC."


@pytest.mark.parametrize(
    "bad_reply",
    [
        "Fue en 1776, pero solo atiendo temas de TechFix.",
        "",
        "x" * 800,
        RuntimeError("timeout"),
    ],
)
def test_reply_falls_back_when_model_leaks_or_fails(bad_reply):
    assert out_of_scope_reply(GuardModel(reply=bad_reply), "¿En qué año...?") == OUT_OF_SCOPE_FALLBACK
