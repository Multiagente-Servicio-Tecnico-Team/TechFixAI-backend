from langchain_core.messages import AIMessage, HumanMessage

from app.agents.orquestador.agentes.confirmation import parse_confirmation
from app.agents.orquestador.graph.state import AgentState, IntakeResult
from app.config import create_chat_model


def atencion_node(state: AgentState) -> dict[str, object]:
    latest = next(
        (str(message.content).strip() for message in reversed(state.get("messages", []))
         if isinstance(message, HumanMessage)),
        "",
    )
    import re
    normalized = latest.casefold()
    build_request = re.search(
        r"\b(?:armado (?:de )?pc|armar (?:una )?pc|ensamblar (?:una )?pc|pc gamer|pc para juegos)\b",
        normalized,
    )
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
            response = "Confirmación recibida. Guardaré el ticket y el presupuesto sugerido."
            return {
                "ticket_confirmed": True,
                "awaiting_ticket_confirmation": False,
                "response": response,
                "messages": [AIMessage(content=response)],
            }

        if confirmation is False:
            response = "De acuerdo. No guardé el ticket ni el presupuesto. Puedes iniciar una nueva consulta cuando quieras."
            return {
                "ticket_confirmed": False,
                "ticket_cancelled": True,
                "awaiting_ticket_confirmation": False,
                "response": response,
                "messages": [AIMessage(content=response)],
            }

        response = "Para seguir, responde **Sí, confirmo** para guardar el ticket y el presupuesto, o **No** para descartarlos."
        return {
            "awaiting_ticket_confirmation": True,
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    model = create_chat_model().with_structured_output(IntakeResult)
    result = model.invoke(
        [
            (
                "system",
                "Eres atención al cliente. Extrae equipo, marca/modelo, síntomas e intención. "
                "Redacta todos los campos en español. Si el usuario escribe los síntomas en inglés "
                "u otro idioma, tradúcelos al español sin cambiar ni omitir información. "
                "Conserva marcas, modelos, códigos y nombres propios. Nunca copies la descripción "
                "en inglés en el campo symptoms. "
                "Pregunta antes de derivar cuando falte información esencial. "
                "Clasifica una falla de equipo como 'Soporte técnico'.",
            ),
            *state.get("messages", []),
        ]
    )
    values: dict[str, object] = {
        "category": "Soporte técnico",
        "product": result.product,
        "symptoms": result.symptoms,
        "awaiting_clarification": result.needs_clarification,
        "clarification": result.clarification_question,
        "awaiting_ticket_confirmation": False,
        "ticket_confirmed": False,
    }

    if result.needs_clarification:
        question = result.clarification_question or "¿Podrías compartir la marca, el modelo y cuándo ocurre la falla?"
        values["clarification"] = question
        values["response"] = question
        values["messages"] = [AIMessage(content=question)]
    return values
