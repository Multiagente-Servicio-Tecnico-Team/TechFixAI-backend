from decimal import Decimal
from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.agents.orquestador.agentes.pc_build import pc_build_node


def test_orchestrator_lists_only_live_profiles_and_waits_for_selection(monkeypatch):
    import app.agents.orquestador.agentes.pc_build as module

    option = {"code": "gaming-inicial", "name": "PC gamer inicial",
              "parts": [{"code": "CPU-1", "name": "CPU", "category": "CPU",
                         "quantity": 1, "unit_price": Decimal("200"),
                         "subtotal": Decimal("200")}],
              "labor_cost": Decimal("50"), "total": Decimal("250"),
              "within_budget": True,
              "compatibility_notes": "Revisión final necesaria."}
    monkeypatch.setattr(module, "ServiceRepository", lambda: object())
    monkeypatch.setattr(module, "load_settings", lambda: SimpleNamespace(
        labor_price_for=lambda _task: Decimal("50")
    ))
    monkeypatch.setattr(module, "available_pc_builds", lambda *a, **kw: [option])

    result = pc_build_node({
        "build_intended_use": "gaming", "messages": [HumanMessage(content="Quiero armar PC gamer")]
    })
    assert result["awaiting_build_selection"] is True
    assert result["build_options"][0]["code"] == "gaming-inicial"
    assert "S/ 250.00" in result["messages"][0].content


def test_orchestrator_selection_keeps_server_calculated_parts(monkeypatch):
    option = {"code": "gaming-inicial", "name": "PC gamer inicial",
              "parts": [{"code": "CPU-1", "name": "CPU", "category": "CPU",
                         "quantity": 1, "unit_price": Decimal("200"),
                         "subtotal": Decimal("200")}],
              "labor_cost": Decimal("50"), "total": Decimal("250"),
              "within_budget": True,
              "compatibility_notes": "Revisión final necesaria."}
    result = pc_build_node({
        "build_intended_use": "gaming", "awaiting_build_selection": True,
        "build_options": [option],
        "messages": [HumanMessage(content="Elijo el primero")],
    })
    assert result["pc_build_selected"] is True
    assert result["matched_parts"] == option["parts"]
    assert result["build_total"] == Decimal("250")
