import unittest

from app.agents.orquestador.knowledge import retrieve_technical_knowledge


class TechnicalKnowledgeTests(unittest.TestCase):
    def test_retrieves_matching_thermal_failure(self):
        passages = retrieve_technical_knowledge(
            "laptop HP se calienta y se apaga con ventilador ruidoso"
        )

        self.assertTrue(passages)
        self.assertIn("Sobrecalentamiento", passages[0])
        self.assertIn("ventilador", passages[0].casefold())

    def test_retrieval_normalizes_accents(self):
        passages = retrieve_technical_knowledge("batería no carga y dura poco")

        self.assertTrue(passages)
        self.assertIn("Bateria no carga", passages[0])

    def test_returns_no_context_for_unrelated_query(self):
        self.assertEqual(retrieve_technical_knowledge("impresora no escanea"), [])


if __name__ == "__main__":
    unittest.main()