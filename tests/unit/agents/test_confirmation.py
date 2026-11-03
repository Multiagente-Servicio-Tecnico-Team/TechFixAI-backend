import unittest

from app.agents.orquestador.agentes.confirmation import parse_confirmation
from app.application.quotes import interpret_quote_decision


class TicketConfirmationTests(unittest.TestCase):
    def test_accepts_explicit_affirmative(self):
        for message in ("Sí", "si confirmo", "Confirmo", "de acuerdo"):
            with self.subTest(message=message):
                self.assertIs(parse_confirmation(message), True)

    def test_accepts_explicit_negative(self):
        for message in ("No", "no gracias", "cancelar"):
            with self.subTest(message=message):
                self.assertIs(parse_confirmation(message), False)

    def test_does_not_treat_unrelated_text_as_consent(self):
        for message in ("tal vez", "síntomas", "sí, pero después"):
            with self.subTest(message=message):
                self.assertIsNone(parse_confirmation(message))

    def test_orchestrator_confirmation_matches_shared_quote_policy(self):
        decisions = {
            "si": (True, "ACCEPT"),
            "si confirmo": (True, "ACCEPT"),
            "de acuerdo": (True, "ACCEPT"),
            "no": (False, "REJECT"),
            "no gracias": (False, "REJECT"),
            "rechazo": (False, "REJECT"),
            "lo voy a revisar": (None, None),
        }

        for message, (orchestrator_decision, shared_decision) in decisions.items():
            with self.subTest(message=message):
                self.assertIs(parse_confirmation(message), orchestrator_decision)
                self.assertEqual(interpret_quote_decision(message), shared_decision)

if __name__ == "__main__":
    unittest.main()
