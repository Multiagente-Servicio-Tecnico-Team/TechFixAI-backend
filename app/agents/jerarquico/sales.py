from typing import Any
from decimal import Decimal
from datetime import UTC, datetime, timedelta

from langchain_core.messages import AIMessage

from app.agents.jerarquico.graph.state import ServiceState
from app.settings import Settings
from app.agents.jerarquico.tools.quotes import calculate_quote
from app.application.quotes import quote_changed


def make_sales_agent(settings: Settings, direct_sales_quotes=None):
    if direct_sales_quotes is None:
        from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter
        direct_sales_quotes = SalesQuoteRepositoryAdapter()

    def persist_sale_quote(state, quote):
        return direct_sales_quotes.create_direct_sales_quote(
            customer_id=int(state["customer_id"]), actor_user_id=None,
            lines=[{"spare_part_id": int(part.get("inventory_id") or part.get("id")), "quantity": int(part["quantity"])}
                   for part in quote["parts"]],
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            quote_type=quote["quote_type"],
            labor_cost=quote["labor_cost"],
            observations=(
                "Cotización generada desde el chat; el cliente aún debe aceptarla."
                + (f" Armado recomendado: {state.get('build_profile_id', '')}."
                   if state.get("request_type") == "PC_BUILD" else "")
            ),
            origin="PORTAL",
        )

    def sales_agent(state: ServiceState) -> dict[str, Any]:
        if state.get("request_type") == "SALE" and state.get("route") == "declined":
            if state.get("quote_id"):
                direct_sales_quotes.resolve_direct_sales_quote(
                    quote_id=state["quote_id"], customer_id=int(state["customer_id"]),
                    actor_user_id=None, target_status="REJECTED", notes="Rechazada desde el chat.",
                )
            return {"route": "service", "outcome": "declined", "messages": [
                AIMessage(content="Entendido. Rechacé la cotización de venta; no se reservó inventario ni se registró un pago.")
            ]}
        request_type = state["request_type"]
        if request_type == "SALE":
            labor_task_type = "sale"
        elif request_type == "PC_BUILD":
            labor_task_type = "pc_build"
        else:
            labor_task_type = state["labor_task_type"]
        labor_cost = Decimal("0.00") if request_type == "SALE" else settings.labor_price_for(labor_task_type)
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
        quote_id = state.get("quote_id")
        if state.get("route") == "confirm" and state.get("quote"):
            previous = state["quote"]
            if quote_changed(previous, quote):
                if request_type in {"SALE", "PC_BUILD"} and quote_id:
                    direct_sales_quotes.resolve_direct_sales_quote(
                        quote_id=quote_id, customer_id=int(state["customer_id"]),
                        actor_user_id=None, target_status="CANCELLED",
                        notes="Reemplazada porque cambió el precio o disponibilidad.",
                    )
                    quote_id = int(persist_sale_quote(state, quote)["id"])
                return {
                    "quote": quote,
                    "quote_id": quote_id,
                    "route": "service",
                    "outcome": "price_changed",
                    "quote_changed": True,
                }
        if request_type in {"SALE", "PC_BUILD"}:
            previous = state.get("quote")
            if quote_id is not None and previous and quote_changed(previous, quote):
                # El cliente cambió artículos: la cotización guardada ya no es la que verá ni aceptará.
                direct_sales_quotes.resolve_direct_sales_quote(
                    quote_id=quote_id, customer_id=int(state["customer_id"]),
                    actor_user_id=None, target_status="CANCELLED",
                    notes="Reemplazada porque el cliente modificó los artículos.",
                )
                quote_id = None
            if quote_id is None:
                quote_id = int(persist_sale_quote(state, quote)["id"])
        return {"quote": quote, "quote_type": quote_type, "quote_id": quote_id}

    return sales_agent


def quote_suggestion_response(state: ServiceState) -> dict[str, Any]:
    if state.get("request_type") == "SALE" and state.get("outcome") == "declined":
        return {
            "route": "service", "outcome": "declined", "awaiting_quote_confirmation": False,
            "messages": [AIMessage(content="Entendido. Rechacé la cotización de venta; no se reservó inventario ni se registró un pago.")],
        }
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
    if state.get("request_type") in {"SALE", "PC_BUILD"}:
        quote_label = (
            "cotización de venta directa"
            if state["request_type"] == "SALE"
            else "cotización de armado de PC"
        )
        quote_reference = (
            f" #{state['quote_id']}" if state.get("quote_id") is not None else ""
        )
        lines.extend([
            f"Los productos suman S/ {quote['parts_cost']:.2f}; el total es S/ {quote['total_amount']:.2f}.",
            (f"La {quote_label}{quote_reference} quedó guardada como pendiente. "
             "No hay ticket de servicio asociado. ¿Aceptas esta propuesta? Responde sí o no."),
        ])
    else:
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
