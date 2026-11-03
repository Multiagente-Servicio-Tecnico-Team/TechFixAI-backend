import unittest

from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever


class MarkdownKnowledgeRetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retriever = MarkdownKnowledgeRetriever()

    def test_recovers_storage_case_from_spanish_symptoms(self):
        queries = (
            "Mi laptop está lenta y tarda mucho en arrancar",
            "Hola, mi laptop está lenta y demora en arrancar",
        )
        for query in queries:
            with self.subTest(query=query):
                results = self.retriever.retrieve(query)

                self.assertGreater(len(results), 0)
                self.assertIn(
                    results[0].title,
                    {
                        "Uso de disco al 100% y equipo lento",
                        "Laptop lenta y demora en abrir aplicaciones",
                    },
                )
                self.assertEqual(
                    results[0].recommended_parts[0].identifier,
                    "SSD_1TB",
                )

    def test_recovers_battery_case_across_accents_and_synonyms(self):
        results = self.retriever.retrieve("la batería no retiene carga")

        self.assertEqual(results[0].title, "Laptop no carga o la batería dura poco")
        self.assertEqual(results[0].recommended_parts[0].identifier, "REP-BAT-L2023")

    def test_recovers_ssd_case_for_laptop_slow_to_open_applications(self):
        results = self.retriever.retrieve(
            "Mi laptop está lenta y demora mucho en abrir aplicaciones"
        )

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].title, "Laptop lenta y demora en abrir aplicaciones")
        self.assertEqual(results[0].recommended_parts[0].identifier, "SSD_1TB")

    def test_alternatives_require_choosing_one_catalog_identifier(self):
        results = self.retriever.retrieve("PC se apaga poco después de encender")
        self.assertEqual(len(results), 1)
        shutdown_case = next(
            document
            for document in results
            if document.title == "PC se apaga poco después de encender"
        )

        self.assertEqual(shutdown_case.selection_mode, "one")
        self.assertEqual(
            [item.identifier for item in shutdown_case.recommended_parts],
            ["Servicio_Aislamiento_Placa", "Fuente_Poder"],
        )

    def test_context_contains_manual_guidance_but_no_prices(self):
        documents = self.retriever.retrieve("memoria RAM casi llena en reposo")
        context = self.retriever.format_context(documents)

        self.assertIn("RAM_16GB", context)
        self.assertIn("PostgreSQL", context)
        self.assertIn("no definen precios", context)
        self.assertNotIn(" UM", context)
        self.assertNotIn("Rango", context)

    def test_no_unrelated_documents_are_returned(self):
        self.assertEqual(
            self.retriever.retrieve("consulta sobre horario de atención"),
            [],
        )

    def test_limit_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "mayor que cero"):
            self.retriever.retrieve("batería", limit=0)


if __name__ == "__main__":
    unittest.main()
