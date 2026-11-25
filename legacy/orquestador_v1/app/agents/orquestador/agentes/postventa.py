"""Alias de compatibilidad para los antiguos agentes de postventa.

El grafo usa `warranty_agent` y `logistics_agent` como nodos separados. Los
consumidores legacy que todavía importen `postventa_node` conservan el
comportamiento de despacho.
"""

from app.agents.orquestador.agentes.logistics import logistics_node
from app.agents.orquestador.agentes.warranty import warranty_node


def postventa_node(state: dict[str, object]) -> dict[str, object]:
    if state.get("warranty_status_pending") or state.get("warranty_claim_pending"):
        return warranty_node(state)
    if state.get("logistics_pending"):
        return logistics_node(state)
    return {}
