from typing import Any
from decimal import Decimal

from langchain_core.messages import AIMessage

from app.agents.jerarquico.graph.state import ServiceState
from app.settings import Settings
from app.agents.jerarquico.tools.quotes import calculate_quote
from app.application.quotes import quote_changed


def make_sales_agent(settings: Settings):
    def sales_agent(state: ServiceState) -> dict[str, Any]:
        request_type = state["request_type"]
        if request_type == "SALE":
            labor_task_type = "sale"
        elif request_type == "PC_BUILD":
            labor_task_type = "pc_build"
        else:
            labor_task_type = state["labor_task_type"]
        labor_cost = settings.labor_price_for(labor_task_type)
        quote = calculate_quote(
            labor_cost=labor_cost,
            labor_task_type=labor_task_type,
            parts=state["matched_parts"],
        )
        quote_type = {
            "SALE": "DIRECT_SALE",
            "PC_BUILD": "PC_BUILD",
        }.get(request_type, "REPAIR")
        quote["quote_type"] = quote_type
        if state.get("route") == "confirm" and state.get("quote"):
            previous = state["quote"]
            if quote_changed(previous, quote):
                return {
                    "quote": quote,
                    "route": "service",
                    "outcome": "price_changed",
                    "quote_changed": True,
                }
        return {"quote": quote, "quote_type": quote_type}

    return sales_agent


def quote_suggestion_response(state: ServiceState) -> dict[str, Any]:
    quote = state["quote"]
    if state["request_type"] == "SALE":
        lines = ["Revisé los artículos solicitados contra el inventario actual:"]
    elif state["request_type"] == "PC_BUILD":
        lines = [
            (
                f"Armado recomendado: {state.get('build_profile_id', '').replace('-', ' ')}. "
                "Los productos, stock y precios se consultaron en el catálogo "
                "actual. La compatibilidad integral requiere validar: "
                f"{state.get('build_compatibility_notes', 'revisión final del fabricante')}."
            )
        ]
    elif state["labor_task_type"] == "diagnosis":
        diagnosis_context = (
            "Con la información disponible todavía no es posible identificar "
            "la causa exacta. "
        )
        if quote["parts"]:
            candidates = ", ".join(
                    part["name"]
                for part in quote["parts"]
            )
            diagnosis_context += (
                f"Como opción provisional, te recomiendo evaluar {candidates}; "
                "consulté su disponibilidad y precio en el catálogo. El técnico "
                "debe confirmar que el almacenamiento sea la causa y verificar "
                "la compatibilidad con el modelo antes de instalarlo. "
            )
        diagnosis_context += (
            f"El ticket {state['ticket_code']} ya está registrado para que el "
            "técnico revise el equipo y diagnostique la falla."
        )
        if not quote["parts"]:
            diagnosis_context += (
                f" El presupuesto sería únicamente de mano de obra por "
                f"S/ {quote['labor_cost']:.2f}; los repuestos quedan en "
                "S/ 0.00 porque todavía no se ha determinado cuáles se necesitan."
            )
        lines = [diagnosis_context]
    else:
        lines = [
            (
                "Por lo que describes, podría tratarse de: "
                f"{state['provisional_diagnosis'].rstrip('. ')}. "
                "Aún es preliminar y el técnico deberá revisar el equipo."
            )
        ]
    if state.get("quote_changed"):
        lines.append(
            "Desde la propuesta anterior cambió el stock, un precio o el costo fijo "
            "de mano de obra. Te comparto los valores actualizados para que los "
            "revises antes de confirmar."
        )
    for substitution in state.get("inventory_substitutions", []):
        quoted_part = next(
            (
                part
                for part in quote["parts"]
                if part["code"] == substitution["suggested_code"]
            ),
            None,
        )
        price_detail = (
            f" Está a S/ {quoted_part['unit_price']:.2f} por unidad y hay "
            f"{quoted_part['current_stock']} en stock."
            if quoted_part
            else ""
        )
        lines.append(
            f"No tenemos disponible {substitution['requested_code']}, pero sí "
            f"{substitution['suggested_name']} ({substitution['suggested_code']})."
            f"{price_detail} Podría servir como alternativa; el técnico debe "
            "confirmar que sea compatible con tu equipo."
        )
    substitution_codes = {
        substitution["suggested_code"]
        for substitution in state.get("inventory_substitutions", [])
    }
    other_parts = [
        part for part in quote["parts"] if part["code"] not in substitution_codes
    ]
    if other_parts:
        part_names = ", ".join(
            f"{part['name']} x {part['quantity']} (S/ {part['subtotal']:.2f})"
            for part in other_parts
        )
        lines.append(f"Para la propuesta consideré: {part_names}.")
    elif not quote["parts"] and quote["labor_task_type"] != "diagnosis":
        lines.append("Por ahora no hace falta incluir un repuesto específico.")
    lines.extend(
        [
            (
                f"El costo fijo de mano de obra por "
                f"{'diagnóstico' if quote['labor_task_type'] == 'diagnosis' else 'ensamble' if quote['labor_task_type'] == 'pc_build' else 'mantenimiento/cambio de partes' if quote['labor_task_type'] == 'maintenance' else 'venta directa'} "
                f"es S/ {quote['labor_cost']:.2f}."
            ),
            f"Los repuestos suman S/ {quote['parts_cost']:.2f}; "
            f"el total provisional es S/ {quote['total_amount']:.2f}.",
            (
                f"El ticket {state['ticket_code']} ya está registrado. "
                "Todavía no he guardado la cotización. ¿Aceptas esta propuesta? "
                "Responde sí o no."
            ),
        ]
    )
    budget = state.get("budget_max")
    if (
        state.get("request_type") == "PC_BUILD"
        and budget is not None
        and quote["total_amount"] > Decimal(str(budget))
    ):
        lines.insert(
            1,
            (
                f"Nota: el total de S/ {quote['total_amount']:.2f} supera el "
                f"presupuesto indicado de S/ {Decimal(str(budget)):.2f}. "
                "Solo continuaré si confirmas explícitamente este nuevo importe."
            ),
        )
    return {
        "route": "service",
        "outcome": "awaiting_confirmation",
        "awaiting_quote_confirmation": True,
        "quote_changed": False,
        "messages": [AIMessage(content="\n".join(lines))],
    }
