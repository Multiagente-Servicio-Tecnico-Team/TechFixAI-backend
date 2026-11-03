import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from app.settings import Settings, load_settings


class SettingsTests(unittest.TestCase):
    def load_from_environment(self, values: dict[str, str]) -> Settings:
        with patch.dict(os.environ, values, clear=True):
            with patch("app.settings.load_dotenv"):
                return load_settings()

    def test_loads_agent_database_and_tracing_settings(self):
        settings = self.load_from_environment(
            {
                "GROQ_API_KEY": "groq-secret",
                "GROQ_MODEL": "test-model",
                "DATABASE_URL": "postgresql+pg8000://user:password@localhost/db",
                "LANGSMITH_API_KEY": "langsmith-secret",
                "LANGSMITH_TRACING": "true",
                "LABOR_MAINTENANCE_PRICE": "45.50",
                "LABOR_DIAGNOSIS_PRICE": "55.00",
            }
        )

        self.assertEqual(settings.groq_model, "test-model")
        self.assertTrue(settings.langsmith_tracing)
        self.assertTrue(settings.langsmith_hide_inputs)
        self.assertTrue(settings.langsmith_hide_outputs)
        self.assertEqual(settings.labor_maintenance_price, Decimal("45.50"))
        self.assertEqual(settings.labor_diagnosis_price, Decimal("55.00"))
        settings.require_chat_configuration()

    def test_missing_tracing_key_is_reported(self):
        settings = self.load_from_environment(
            {
                "GROQ_API_KEY": "groq-secret",
                "GROQ_MODEL": "test-model",
                "DATABASE_URL": "postgresql+pg8000://localhost/db",
                "LANGSMITH_TRACING": "true",
            }
        )

        with self.assertRaisesRegex(RuntimeError, "LANGSMITH_API_KEY"):
            settings.require_chat_configuration()

    def test_langsmith_trace_redaction_can_be_explicitly_disabled(self):
        settings = self.load_from_environment(
            {
                "LANGSMITH_HIDE_INPUTS": "false",
                "LANGSMITH_HIDE_OUTPUTS": "false",
            }
        )

        self.assertFalse(settings.langsmith_hide_inputs)
        self.assertFalse(settings.langsmith_hide_outputs)

    def test_sensitive_settings_are_not_in_repr(self):
        settings = self.load_from_environment(
            {
                "GROQ_API_KEY": "groq-secret",
                "GROQ_MODEL": "test-model",
                "DATABASE_URL": "postgresql+pg8000://user:password@localhost/db",
                "LANGSMITH_API_KEY": "langsmith-secret",
            }
        )

        rendered = repr(settings)
        self.assertNotIn("groq-secret", rendered)
        self.assertNotIn("langsmith-secret", rendered)
        self.assertNotIn("password", rendered)

    def test_labor_prices_have_fixed_defaults_in_peruvian_soles(self):
        settings = self.load_from_environment({})

        self.assertEqual(settings.labor_maintenance_price, Decimal("35.00"))
        self.assertEqual(settings.labor_diagnosis_price, Decimal("50.00"))

    def test_rejects_nonpositive_fixed_labor_prices(self):
        for key, value in (
            ("LABOR_MAINTENANCE_PRICE", "0"),
            ("LABOR_DIAGNOSIS_PRICE", "-1"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.load_from_environment({key: value})

    def test_rejects_invalid_tracing_flag(self):
        with self.assertRaisesRegex(ValueError, "LANGSMITH_TRACING"):
            self.load_from_environment({"LANGSMITH_TRACING": "sometimes"})

    def test_audio_is_disabled_by_default_and_limits_have_expected_values(self):
        settings = self.load_from_environment({})
        self.assertFalse(settings.audio_transcription_enabled)
        self.assertEqual(settings.audio_transcription_timeout_seconds, 30)
        self.assertEqual(settings.audio_max_bytes, 25_000_000)
        self.assertEqual(settings.audio_max_duration_ms, 120_000)
        self.assertEqual(settings.audio_requests_per_minute, 5)

    def test_audio_with_visible_langsmith_payload_is_rejected(self):
        settings = self.load_from_environment({
            "AUDIO_TRANSCRIPTION_ENABLED": "true",
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "secret",
            "LANGSMITH_HIDE_INPUTS": "false",
        })
        with self.assertRaisesRegex(RuntimeError, "LANGSMITH_HIDE_INPUTS"):
            settings.validate_audio_privacy()

    def test_rejects_invalid_audio_timeout_or_limits(self):
        for name, value in (("AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS", "0"), ("AUDIO_MAX_BYTES", "-1"), ("AUDIO_REQUESTS_PER_MINUTE", "many")):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                self.load_from_environment({name: value})


if __name__ == "__main__":
    unittest.main()
