from app.agents.orquestador.graph.state import AgentState
from app.agents.orquestador.tools import consultar_inventario


def almacen_node(state: AgentState) -> dict[str, object]:
    inventory = [
        consultar_inventario.invoke(
            {"nombre_repuesto": part["name"], "cantidad": part["quantity"]}
        )
        for part in state.get("requested_parts", [])
    ]
    return {"inventory": inventory}