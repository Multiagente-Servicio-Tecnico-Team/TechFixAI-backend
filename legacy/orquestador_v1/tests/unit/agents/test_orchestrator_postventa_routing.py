from langchain_core.messages import HumanMessage

from app.agents.orquestador.agentes.atencion import atencion_node
from app.agents.orquestador.graph.supervisor import _supervisor_route


def test_warranty_query_routes_by_exact_policy_code():
    result = atencion_node({
        "messages": [HumanMessage(content="¿Estado de la garantía WAR-ABC123?")]
    })
    assert result["warranty_code"] == "WAR-ABC123"
    assert result["warranty_status_pending"] is True
    assert _supervisor_route(result) == "warranty_agent"


def test_warranty_claim_collects_owned_ticket_reference():
    result = atencion_node({
        "messages": [HumanMessage(content="Reportar falla con WAR-ABC123 en ticket TCK-123")]
    })
    assert result["warranty_claim_pending"] is True
    assert result["ticket_code"] == "TCK-123"
    assert _supervisor_route(result) == "warranty_agent"


def test_logistics_preference_routes_and_keeps_pending_followup():
    result = atencion_node({
        "messages": [HumanMessage(content="Prefiero retiro presencial")]
    })
    assert result["logistics_pending"] is True
    assert _supervisor_route(result) == "logistics_agent"
    resumed = atencion_node({
        "logistics_pending": True,
        "messages": [HumanMessage(content="Courier Uno, Calle 7")],
    })
    assert resumed["logistics_pending"] is True


def test_pc_build_request_routes_to_inventory_backed_profile_selection():
    result = atencion_node({
        "messages": [HumanMessage(content="Quiero armar una PC gamer hasta 3000")]
    })
    assert result["pc_build_pending"] is True
    assert result["build_intended_use"] == "juegos"
    assert result["build_budget_max"] == 3000
    assert _supervisor_route(result) == "sales_agent"
