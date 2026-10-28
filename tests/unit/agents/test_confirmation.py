import unittest

from app.agents.orquestador.agentes.confirmation import parse_confirmation


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

if __name__ == "__main__":
    unittest.main()