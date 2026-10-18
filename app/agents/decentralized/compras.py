"""Compras consultivo determinista: declara las capacidades disponibles."""
from langchain_core.messages import AIMessage, ToolMessage
from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import evaluate_supply, handoff
from app.agents.decentralized.tools.compras_tools import consultar_fuentes_abastecimiento, transferir_a_ventas

compras_tools = [consultar_fuentes_abastecimiento, transferir_a_ventas]


def compras_node(state: AgentState):
    evaluation = evaluate_supply(state)
    if evaluation["destination"] != "compras":
        return {"current_agent": "compras", "supplier_offers": [], "out_of_stock_items": [], "messages": [AIMessage(content=(
            "No hay un faltante vigente confirmado para evaluar. Es necesario aclarar o verificar el inventario."
        ))]}
    messages = state.get("messages", [])[state.get("turn_start_index", 0):]
    previous = [message for message in messages if isinstance(message, ToolMessage)
                and message.name == "consultar_fuentes_abastecimiento"]
    if not previous:
        return handoff("compras", "consultar_fuentes_abastecimiento")
    if previous[-1].status == "error":
        return {"current_agent": "compras", "supplier_offers": [], "messages": [AIMessage(content="No fue posible verificar las fuentes de abastecimiento; no hay una oferta confirmada.")]}
    offers = [{"status": "PRICE_UNAVAILABLE", "request": item,
               "source": "Sin integración de ofertas externas configurada",
               "missing_fields": ["proveedor verificado", "costo", "moneda", "oferta vigente", "plazo confirmado"]}
              for item in evaluation["out_of_stock_items"]]
    update = handoff("compras", "transferir_a_ventas", motivo="Faltantes confirmados; no hay fuente verificable de ofertas, costos ni plazos")
    update.update(out_of_stock_items=evaluation["out_of_stock_items"], supplier_offers=offers)
    return update
