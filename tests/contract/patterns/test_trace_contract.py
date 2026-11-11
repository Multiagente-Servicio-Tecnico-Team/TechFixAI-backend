from app.adapters.patterns.registry import build_patterns


def test_every_pattern_emits_only_stable_trace_identifiers(pattern_settings):
    patterns = build_patterns(settings_factory=lambda: pattern_settings)

    for pattern_id, pattern in patterns.items():
        config = pattern.config("conversation-123")
        metadata = config["metadata"]
        assert metadata["pattern_id"] == pattern_id
        assert metadata["scenario_id"] == "interactive"
        assert metadata["model_profile_id"] == "groq:contract-model:temperature=0:parallel_tool_calls=false"
        assert config["tags"] == [
            "service-chat", f"pattern:{pattern_id}", "scenario:interactive"
        ]
        assert "customer" not in str(metadata).casefold()
        assert "conversation" not in str(metadata).casefold()
