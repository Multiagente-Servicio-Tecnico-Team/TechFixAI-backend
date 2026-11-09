from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orquestador.agentes.confirmation import parse_confirmation
from app.agents.orquestador.graph.state import AgentState, IntakeResult
from app.config import CURRENCY_SYMBOL, create_chat_model
from app.application.prompts import build_system_prompt


def atencion_node(state: AgentState) -> dict[str, object]:
    latest = next(
        (str(message.content).strip() for message in reversed(state.get("messages", []))
         if isinstance(message, HumanMessage)),
        "",
    )
    import re
    normalized = latest.casefold()
    direct_sale_intent = re.search(
        r"\b(?:quiero|quisiera|necesito|deseo|solicito)\b.{0,35}\b(?:comprar|adquirir)\b",
        normalized,
    )
    build_request = re.search(
        r"\b(?:armado (?:de )?pc|armar (?:una )?pc|ensamblar (?:una )?pc|pc gamer|pc para juegos)\b",
        normalized,
    ) and not direct_sale_intent
    build_followup = state.get("awaiting_build_selection") or state.get("pc_build_collecting_use")
    build_modification = state.get("pc_build_selected") and re.search(
        r"\b(?:cambia|cambiar|reemplaza|reemplazar|modifica|modificar)\b", normalized
    )
    if build_request or build_followup or build_modification:
        intent = state.get("build_intended_use", "")
        if re.search(r"\b(?:juegos|gamer|gaming|videojuegos)\b", normalized):
            intent = "juegos"
        elif re.search(r"\boficina\b", normalized):
            intent = "oficina"
        elif re.search(r"\bestudio\b", normalized):
            intent = "estudio"
        budget = state.get("build_budget_max")
        budget_match = re.search(r"\b(?:presupuesto|tope|hasta)\D{0,12}(\d{3,7})\b", normalized)
        if budget_match:
            budget = int(budget_match.group(1))
        return {"pc_build_pending": True, "pc_build_collecting_use": not bool(intent),
                "build_intended_use": intent, "build_budget_max": budget}
    if state.get("logistics_pending"):
        return {"logistics_pending": True}
    if state.get("warranty_status_pending"):
        return {"warranty_status_pending": True}
    if state.get("warranty_claim_pending"):
        ticket_match = re.search(r"\bTCK-[A-Z0-9-]{2,20}\b", latest, re.IGNORECASE)
        return {
            "warranty_claim_pending": True,
            "ticket_code": ticket_match.group(0).upper() if ticket_match else state.get("ticket_code", ""),
        }
    warranty_match = re.search(r"\bWAR-[A-Z0-9-]{2,28}\b", latest, re.IGNORECASE)
    if warranty_match:
        code = warranty_match.group(0).upper()
        if re.search(r"\b(reclamo|reclamar|falla|problema|dañ|dano)\b", latest, re.IGNORECASE):
            ticket_match = re.search(r"\bTCK-[A-Z0-9-]{2,20}\b", latest, re.IGNORECASE)
            return {
                "warranty_code": code,
                "warranty_claim_pending": True,
                "warranty_status_pending": False,
                "ticket_code": ticket_match.group(0).upper() if ticket_match else "",
            }
        return {"warranty_code": code, "warranty_status_pending": True,
                "warranty_claim_pending": False}
    if re.search(r"\b(retiro presencial|retirar en tienda|env[ií]o por courier|courier)\b", latest, re.IGNORECASE):
        return {"logistics_pending": True}
    ticket_match = re.search(r"\bTCK-[A-Z0-9-]{2,20}\b", latest, re.IGNORECASE)
    if ticket_match and re.search(r"\b(ticket|caso|solicitud)\b", latest, re.IGNORECASE):
        return {"ticket_code": ticket_match.group(0).upper(), "ticket_lookup_pending": True}
    if state.get("awaiting_refund_details") or re.search(
        r"\b(?:reembolso|reembolsar|devoluci[oó]n de dinero|devolver el dinero)\b",
        latest.casefold(),
    ):
        return {"awaiting_refund_details": True, "refund_request_pending": True}
    if re.search(
        r"\b(?:comprar|compra|conseguir|pedir)\b.{0,50}\bproveedor(?:es)?\b|\bproveedor(?:es)?\b.{0,50}\b(?:comprar|compra|conseguir|pedir)\b",
        latest.casefold(),
    ):
        return {"supplier_procurement_pending": True}

    if state.get("awaiting_sales_quote_confirmation"):
        quote_id = state.get("sales_quote_id")
        customer_id = state.get("user_id")
        if type(quote_id) is not int or quote_id < 1 or type(customer_id) is not int or customer_id < 1:
            response = "No pude recuperar la cotización pendiente. Vuelve a solicitar el armado para crear una propuesta nueva."
            return {"awaiting_sales_quote_confirmation": False,
                    "sales_quote_status": "UNAVAILABLE", "pc_build_selected": False,
                    "response": response, "messages": [AIMessage(content=response)]}

        confirmation = parse_confirmation(latest)
        from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter
        quotes = SalesQuoteRepositoryAdapter()
        if confirmation is True:
            accepted = None
            try:
                accepted = quotes.accept_direct_sales_quote(
                    quote_id=quote_id, customer_id=customer_id, actor_user_id=None,
                    idempotency_key=f"orchestrator-chat-{quote_id}", confirmation_channel="CHAT",
                )
            except (LookupError, ValueError, PermissionError):
                try:
                    quotes.resolve_direct_sales_quote(
                        quote_id=quote_id, customer_id=customer_id, actor_user_id=None,
                        target_status="CANCELLED",
                        notes="Cotización de armado ya no aceptable por cambios de disponibilidad.",
                    )
                    status = "CANCELLED"
                except (LookupError, ValueError, PermissionError):
                    status = "UNAVAILABLE"
                response = "No pude aceptar la cotización porque el stock o su vigencia cambió. No reservé artículos; solicita una cotización actualizada."
            else:
                status = accepted.get("status", "UNAVAILABLE")
                if accepted.get("error"):
                    response = str(accepted["error"])
                else:
                    kind = state.get("sales_quote_kind", "PC_BUILD")
                    response = (f"Aceptaste la cotización {kind} #{quote_id}. Reservé los artículos hasta su vencimiento. "
                                f"El pago {accepted.get('payment_code')} por {CURRENCY_SYMBOL} {state.get('build_total', 0):.2f} "
                                "está pendiente; no se creó un ticket de servicio.")
            return {"awaiting_sales_quote_confirmation": False,
                    "sales_quote_status": status,
                    "sales_payment_code": accepted.get("payment_code") if accepted and not accepted.get("error") else None,
                    "pc_build_selected": False,
                    "response": response, "messages": [AIMessage(content=response)]}

        if confirmation is False:
            try:
                result = quotes.resolve_direct_sales_quote(
                    quote_id=quote_id, customer_id=customer_id, actor_user_id=None,
                    target_status="REJECTED", notes="Rechazada explícitamente en el chat.",
                )
            except (LookupError, ValueError, PermissionError):
                response = "No pude actualizar esa cotización. No se hizo ningún cambio; consulta su estado antes de continuar."
                return {"awaiting_sales_quote_confirmation": False,
                        "sales_quote_status": "UNAVAILABLE", "pc_build_selected": False,
                        "response": response, "messages": [AIMessage(content=response)]}
            response = "De acuerdo. Rechacé la cotización; no reservé inventario ni registré un pago."
            return {"awaiting_sales_quote_confirmation": False,
                    "sales_quote_status": result.get("status", "REJECTED"),
                    "pc_build_selected": False, "response": response,
                    "messages": [AIMessage(content=response)]}

        response = "La cotización sigue pendiente. Responde **Sí, confirmo** para aceptarla o **No** para rechazarla."
        return {"awaiting_sales_quote_confirmation": True, "response": response,
                "messages": [AIMessage(content=response)]}

    if direct_sale_intent or state.get("direct_sale_pending"):
        number_words = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
                        "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
        product = str(state.get("direct_sale_product") or "").strip()
        quantity = state.get("direct_sale_quantity")
        candidates = list(state.get("direct_sale_candidates") or [])
        if direct_sale_intent:
            purchase = re.search(
                r"\b(?:comprar|adquirir)\s+(?:(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+)?([^;\n]+)",
                latest, re.IGNORECASE,
            )
            if purchase:
                raw_quantity = purchase.group(1)
                product = purchase.group(2).strip(" .!?\n")
                quantity = (int(raw_quantity) if raw_quantity.isdigit()
                            else number_words.get(raw_quantity.casefold()) if raw_quantity else None)
            candidates = []
        elif candidates:
            # The sales node owns candidate matching and catalog revalidation.
            pass
        elif type(quantity) is not int or quantity < 1:
            response_number = re.fullmatch(r"\s*(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s*", normalized)
            if response_number:
                raw_quantity = response_number.group(1)
                quantity = int(raw_quantity) if raw_quantity.isdigit() else number_words[raw_quantity]
            elif latest.strip():
                product = latest.strip()
        else:
            # A catalog miss can be refined naturally in the next user turn.
            product = latest.strip() or product
        return {"direct_sale_pending": True, "direct_sale_product": product,
                "direct_sale_quantity": quantity, "direct_sale_candidates": candidates,
                "sales_quote_status": None, "response": "",
                "messages": []}

    if state.get("awaiting_ticket_confirmation"):
        latest_message = next(
            (
                str(message.content)
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        confirmation = parse_confirmation(latest_message)
        if confirmation is True:
            response = "Confirmación recibida. Guardaré la cotización en el ticket de servicio existente."
            return {
                "ticket_confirmed": True,
                "awaiting_ticket_confirmation": False,
                "response": response,
                "messages": [AIMessage(content=response)],
            }

        if confirmation is False:
            response = (
                f"De acuerdo. No guardé la cotización ni registré un pago. "
                f"El ticket {state.get('ticket_code', '')} se conserva para seguimiento; "
                "puedes pedir otra cotización cuando quieras."
            )
            return {
                "ticket_confirmed": False,
                "ticket_cancelled": True,
                "awaiting_ticket_confirmation": False,
                "response": response,
                "messages": [AIMessage(content=response)],
            }

        response = "El ticket ya está registrado. Responde **Sí, confirmo** para guardar esta cotización en el ticket, o **No** para descartarla."
        return {
            "awaiting_ticket_confirmation": True,
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    model = create_chat_model().with_structured_output(IntakeResult)
    result = model.invoke(
        [
            ("system", build_system_prompt(role="CUSTOMER", pattern_id="orchestrator")),
            (
                "system",
                "Eres atención al cliente. Clasifica la intención y extrae equipo, marca/modelo, síntomas e intención. "
                "Usa intent=FAQ para preguntas informativas sobre ubicación, horarios, servicios, "
                "cómo funciona una cotización, tarifas, métodos de pago, garantía o logística. "
                "Si pregunta cómo preparar una cotización, usa FAQ; si pide que prepares una ahora, "
                "es una solicitud de compra o servicio, no una FAQ. "
                "No uses FAQ para diagnosticar o registrar un caso de servicio, ni para consultar "
                "precios/stock actuales del inventario; esas solicitudes son SERVICE o siguen su flujo propio. "
                "Redacta todos los campos en español. Si el usuario escribe los síntomas en inglés "
                "u otro idioma, tradúcelos al español sin cambiar ni omitir información. "
                "Conserva marcas, modelos, códigos y nombres propios. Nunca copies la descripción "
                "en inglés en el campo symptoms. "
                "Pregunta antes de derivar cuando falte información esencial. "
                "Clasifica la solicitud como REPAIR cuando pida reparación del equipo y SUPPORT "
                "cuando pida orientación o diagnóstico sin especificar reparación.",
            ),
            *state.get("messages", []),
        ]
    )
    if result.intent == "FAQ":
        return {
            "faq_pending": True,
            "faq_query": latest,
            "awaiting_clarification": False,
            "response": "",
        }

    values: dict[str, object] = {
        "category": "Reparación" if result.request_type == "REPAIR" else "Soporte técnico",
        "request_type": result.request_type,
        "product": result.product.strip(),
        "symptoms": result.symptoms.strip(),
        "awaiting_clarification": result.needs_clarification,
        "clarification": result.clarification_question,
        "awaiting_ticket_confirmation": False,
        "ticket_confirmed": False,
    }

    if result.needs_clarification or not values["product"] or not values["symptoms"]:
        question = result.clarification_question or "¿Podrías compartir la marca, el modelo y cuándo ocurre la falla?"
        values["clarification"] = question
        values["awaiting_clarification"] = True
        values["response"] = question
        values["messages"] = [AIMessage(content=question)]
    return values
