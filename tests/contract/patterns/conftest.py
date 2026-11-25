from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage

from app.adapters.patterns.registry import PATTERN_CLASSES
from app.settings import Settings


@dataclass
class FakeRepository:
    calls: list[tuple[str, dict]] = field(default_factory=list)

    def record(self, operation: str, **values):
        self.calls.append((operation, values))


@dataclass(frozen=True)
class CustomerContext:
    customer_id: int = 41
    conversation_id: str = "contract-conversation"


class FakeModel:
    """Small deterministic ChatModel double; never calls a provider."""

    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.invocations = []
        self.structured_schemas = []
        self.bound_tools = []

    def invoke(self, messages, **kwargs):
        self.invocations.append((messages, kwargs))
        if self.replies:
            return self.replies.pop(0)
        return AIMessage(content="Respuesta determinista de contrato.")

    def with_structured_output(self, schema, **kwargs):
        self.structured_schemas.append((schema, kwargs))
        return self

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append((tools, kwargs))
        return self


@pytest.fixture
def fake_repository():
    return FakeRepository()


@pytest.fixture
def fake_model():
    return FakeModel()


@pytest.fixture
def customer_context():
    return CustomerContext()


@pytest.fixture
def trace_capture():
    return []


@pytest.fixture
def pattern_settings():
    return Settings(
        groq_api_key="contract-key",
        groq_model="contract-model",
        database_url="postgresql+pg8000://localhost/contract",
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="contract-tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("35.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )


@pytest.fixture
def pattern_ids():
    return {pattern.id for pattern in PATTERN_CLASSES}
