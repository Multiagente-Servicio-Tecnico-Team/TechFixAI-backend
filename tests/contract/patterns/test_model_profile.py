from decimal import Decimal

from app.adapters.patterns.decentralized import DecentralizedPattern
from app.adapters.patterns.hierarchical import HierarchicalPattern
from app.adapters.patterns.orchestrator import OrchestratorPattern
from app.settings import Settings


def test_patterns_share_model_profile_but_keep_distinct_pattern_metadata():
    settings = Settings(
        groq_api_key="test-key",
        groq_model="test-model",
        database_url="postgresql+pg8000://localhost/test",
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("35.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )
    patterns = [
        pattern(settings_factory=lambda: settings)
        for pattern in (HierarchicalPattern, OrchestratorPattern, DecentralizedPattern)
    ]

    configs = [pattern.config("conversation-secret") for pattern in patterns]

    assert {config["metadata"]["model_profile_id"] for config in configs} == {
        "groq:test-model:temperature=0"
    }
    assert {config["metadata"]["pattern_id"] for config in configs} == {
        "hierarchical", "orchestrator", "decentralized"
    }
    assert all("conversation-secret" not in str(config["metadata"]) for config in configs)
