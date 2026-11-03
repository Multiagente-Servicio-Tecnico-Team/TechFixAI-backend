import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from langchain_core.messages import HumanMessage

from app.agents.orquestador.agentes.atencion import atencion_node
from app.agents.orquestador.agentes.ventas import persistencia_node, ventas_node
from app.agents.orquestador.graph.state import IntakeResult
from app.agents.orquestador.graph.supervisor import _supervisor_route
from app.agents.orquestador.graph.supervisor import build_graph


class TicketConfirmationGraphTests(unittest.TestCase):
    def setUp(self):
        self.intake_result = IntakeResult(
            category="Soporte técnico",
            product="Laptop HP Pavilion",
            symptoms="Se calienta y se apaga",
            needs_clarification=False,
            clarification_question="",
        )

    def test_intake_routes_to_technician_without_creating_ticket(self):
        model = Mock()
        model.with_structured_output.return_value = model
        model.invoke.return_value = self.intake_result

        with patch("app.agents.orquestador.agentes.atencion.create_chat_model", return_value=model):
            result = atencion_node(
                {"user_id": 12, "messages": [HumanMessage(content="Laptop HP se apaga")]}
            )

        self.assertFalse(result["awaiting_ticket_confirmation"])
        self.assertNotIn("ticket_id", result)
        self.assertEqual(_supervisor_route(result), "tecnico")

    def test_refund_intent_routes_to_manual_refund_agent_without_llm(self):
        with patch("app.agents.orquestador.agentes.atencion.create_chat_model") as model:
            result = atencion_node({
                "user_id": 12,
                "messages": [HumanMessage(content="Quiero solicitar un reembolso")],
            })

        self.assertTrue(result["awaiting_refund_details"])
        self.assertTrue(result["refund_request_pending"])
        self.assertEqual(_supervisor_route(result), "reembolsos")
        model.assert_not_called()

    def test_supplier_purchase_intent_routes_to_unavailable_response_without_llm(self):
        with patch("app.agents.orquestador.agentes.atencion.create_chat_model") as model:
            result = atencion_node({
                "user_id": 12,
                "messages": [HumanMessage(content="¿Pueden comprar el repuesto al proveedor?")],
            })

        self.assertTrue(result["supplier_procurement_pending"])
        self.assertEqual(_supervisor_route(result), "compras")
        model.assert_not_called()

    def test_supplier_purchase_uses_unavailable_node_in_orchestrator_graph(self):
        with patch("app.agents.orquestador.graph.supervisor.create_chat_model"):
            graph = build_graph()
        result = graph.invoke(
            {
                "user_id": 12,
                "messages": [HumanMessage(content="¿Pueden comprar el repuesto al proveedor?")],
            },
            config={"configurable": {"thread_id": "orchestrator-procurement"}},
        )

        self.assertEqual(result["outcome"], "procurement_unavailable")
        self.assertIn("proveedor", result["messages"][-1].content.casefold())
        self.assertIn("no se creó una orden", result["messages"][-1].content.casefold())

    def test_refund_intent_reaches_pending_refund_response_in_orchestrator_graph(self):
        with patch("app.agents.orquestador.graph.supervisor.create_chat_model"):
            graph = build_graph()
        result = graph.invoke(
            {
                "user_id": 12,
                "messages": [HumanMessage(content="Quiero solicitar un reembolso")],
            },
            config={"configurable": {"thread_id": "orchestrator-refund"}},
        )

        self.assertTrue(result["awaiting_refund_details"])
        self.assertIn("PAY-", result["messages"][-1].content)
        self.assertNotIn("refund_id", result)

    def test_intake_uses_spanish_normalized_symptoms_not_raw_english(self):
        model = Mock()
        model.with_structured_output.return_value = model
        model.invoke.return_value = IntakeResult(
            category="Overheating and noise issue",
            product="Lenovo KK503",
            symptoms="Se sobrecalienta durante la carga y el uso, con un zumbido fuerte.",
            needs_clarification=False,
            clarification_question="",
        )

        with patch("app.agents.orquestador.agentes.atencion.create_chat_model", return_value=model):
            result = atencion_node(
                {
                    "messages": [
                        HumanMessage(
                            content="Overheats quickly while charging and usage, accompanied by a strong buzzing noise. Lenovo KK503."
                        )
                    ]
                }
            )

        self.assertEqual(result["category"], "Soporte técnico")
        self.assertEqual(
            result["symptoms"],
            "Se sobrecalienta durante la carga y el uso, con un zumbido fuerte.",
        )

    def test_affirmative_confirmation_routes_to_atomic_persistence(self):
        state = {
            "user_id": 12,
            "product": "Laptop HP Pavilion",
            "category": "Soporte técnico",
            "symptoms": "Se calienta y se apaga",
            "diagnosis": "Diagnóstico provisional",
            "inventory": [],
            "awaiting_ticket_confirmation": True,
            "quote_preview_ready": True,
            "messages": [HumanMessage(content="Sí, confirmo")],
        }
        result = atencion_node(state)

        self.assertTrue(result["ticket_confirmed"])
        self.assertEqual(_supervisor_route({**state, **result}), "persistencia")

    def test_negative_confirmation_does_not_create_ticket_or_quote(self):
        state = {
            "user_id": 12,
            "product": "Laptop HP Pavilion",
            "category": "Soporte técnico",
            "symptoms": "Se calienta y se apaga",
            "diagnosis": "Diagnóstico provisional",
            "inventory": [],
            "awaiting_ticket_confirmation": True,
            "quote_preview_ready": True,
            "messages": [HumanMessage(content="No")],
        }
        result = atencion_node(state)

        self.assertFalse(result["ticket_confirmed"])
        self.assertFalse(result["awaiting_ticket_confirmation"])
        self.assertEqual(_supervisor_route({**state, **result}), "__end__")

    def test_sales_previews_spanish_quote_without_persisting(self):
        state = {
            "category": "Soporte técnico",
            "product": "Laptop HP Pavilion",
            "symptoms": "Se calienta y se apaga",
            "diagnosis": "Acumulación de polvo y posible desgaste del ventilador.",
            "labor_cost": 100,
            "inventory": [
                {
                    "available": True,
                    "name": "Pasta Térmica Arctic MX-4",
                    "quantity": 1,
                    "unit_price": "9.50",
                }
            ],
        }

        result = ventas_node(state)

        self.assertTrue(result["awaiting_ticket_confirmation"])
        self.assertNotIn("quote_id", result)
        self.assertIn("Falla descrita: Se calienta y se apaga", result["response"])
        self.assertIn("Presupuesto sugerido (todavía no guardado)", result["response"])
        self.assertIn("S/ 109.50", result["response"])

    def test_confirmed_persistence_creates_ticket_and_quote_together(self):
        state = {
            "user_id": 12,
            "product": "Laptop HP Pavilion",
            "category": "Soporte técnico",
            "symptoms": "Se calienta y se apaga",
            "diagnosis": "Diagnóstico provisional",
            "labor_cost": 100,
            "available_parts": [],
            "parts_total": Decimal("0.00"),
            "ticket_confirmed": True,
            "total": 100,
        }
        with patch(
            "app.agents.orquestador.agentes.ventas.sales_repository.create_accepted_ticket_quote",
            return_value={
                "ticket_id": 91, "ticket_code": "TCK-TEST-91", "quote_id": 27,
                "payment_code": "PAY-TEST-91", "payment_status": "PENDING",
                "total_amount": Decimal("100.00"),
            },
        ) as persist:
            result = persistencia_node(state)

        persist.assert_called_once()
        self.assertEqual(result["ticket_id"], 91)
        self.assertEqual(result["quote_id"], 27)
        self.assertEqual(result["ticket_code"], "TCK-TEST-91")
        self.assertEqual(result["payment_code"], "PAY-TEST-91")
        self.assertEqual(result["ticket_status"], "PAYMENT_PENDING")
        self.assertIn("S/ 100.00", result["response"])


if __name__ == "__main__":
    unittest.main()
