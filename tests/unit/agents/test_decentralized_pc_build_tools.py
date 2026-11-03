from decimal import Decimal
from types import SimpleNamespace

import app.agents.decentralized.tools.ventas_tools as tools
import app.agents.decentralized.soporte as soporte
from app.agents.decentralized import ventas
from langchain_core.messages import HumanMessage
from app.application.pc_builds import load_pc_build_profiles


class Repository:
    def __init__(self):
        self.items = {}
        for profile in load_pc_build_profiles():
            for category, code in profile.components:
                self.items[code] = {
                    "id": len(self.items) + 1, "code": code, "name": code,
                    "category": category, "unit_price": Decimal("100"),
                    "current_stock": 2,
                }
        self.items["RAM-TEST-32G"] = {
            "id": 90, "code": "RAM-TEST-32G", "name": "RAM 32GB nueva",
            "category": "RAM Desktop", "unit_price": Decimal("150"),
            "current_stock": 2,
        }

    def find_spare_part_by_code(self, code): return self.items.get(code)


def setup(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(tools, "ServiceRepository", lambda: repository)
    monkeypatch.setattr(tools, "load_settings", lambda: SimpleNamespace(
        labor_price_for=lambda _task: Decimal("50")
    ))
    return repository


def test_decentralized_pc_build_tool_prices_only_complete_current_profiles(monkeypatch):
    setup(monkeypatch)
    result = tools.consultar_armados_pc.invoke({"intended_use": "juegos"})
    assert result
    assert all(option["total"] == Decimal("50") + sum(
        (part["unit_price"] for part in option["parts"]), Decimal("0")
    ) for option in result)
    assert all(option["parts"] for option in result)


def test_decentralized_pc_build_modification_rechecks_catalog_and_budget(monkeypatch):
    setup(monkeypatch)
    result = tools.modificar_armado_pc.invoke({
        "profile_id": "gaming-inicial", "intended_use": "juegos",
        "category": "RAM Desktop", "replacement_code": "RAM-TEST-32G",
    })
    assert result["total"] == Decimal("900")
    assert next(part for part in result["parts"] if part["category"] == "RAM Desktop")["code"] == "RAM-TEST-32G"


def test_decentralized_support_hands_pc_build_requests_to_sales():
    result = soporte.soporte_node({
        "messages": [HumanMessage(content="Quiero armar una PC gamer")],
    })
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "transferir_a_ventas"
    assert tools.consultar_armados_pc in ventas.ventas_tools
    assert tools.modificar_armado_pc in ventas.ventas_tools
