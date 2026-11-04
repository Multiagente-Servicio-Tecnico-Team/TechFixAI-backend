"""Non-persistent PC build selection flow for the supervisor graph."""

import re
import unicodedata
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage

from app.application.pc_builds import available_pc_builds, replace_pc_build_component
from app.config import CURRENCY_SYMBOL
from app.database.repository import ServiceRepository
from app.settings import load_settings


def _normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(char) != "Mn"
    )


def _latest_user(state: dict[str, object]) -> str:
    return next((str(message.content).strip() for message in reversed(state.get("messages", []))
                 if isinstance(message, HumanMessage)), "")


def _select_option(text: str, options: list[dict[str, object]]):
    normalized = _normalize(text)
    for option in options:
        if str(option["code"]).casefold() in normalized or _normalize(str(option["name"])) in normalized:
            return option
    index_match = re.search(r"\b(?:opci[oó]n\s*)?(\d+)\b", normalized)
    if not index_match:
        ordinal = next((index for word, index in (("primera", 0), ("primero", 0),
                       ("segunda", 1), ("segundo", 1), ("tercera", 2), ("tercero", 2))
                       if word in normalized), None)
        return options[ordinal] if ordinal is not None and ordinal < len(options) else None
    index = int(index_match.group(1)) - 1
    return options[index] if 0 <= index < len(options) else None


def pc_build_node(state: dict[str, object]) -> dict[str, object]:
    latest = _latest_user(state)
    if state.get("pc_build_selected"):
        match = re.search(
            r"(?:cambia|cambiar|reemplaza|reemplazar|modifica|modificar)\s+"
            r"(?:la\s+|el\s+)?(?P<category>ram|memoria|ssd|almacenamiento|gpu|tarjeta de video)\s+"
            r"(?:por|a)\s+(?P<code>[A-Z0-9][A-Z0-9_-]{2,40})",
            latest,
            re.IGNORECASE,
        )
        if not match:
            reply = "Para cambiar un componente, indica su categoría y el código exacto del catálogo."
            return {"pc_build_selected": True, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        parts = list(state.get("matched_parts", []))
        normalized_category = _normalize(match.group("category"))
        category = None
        for part in parts:
            part_category = _normalize(str(part["category"]))
            matches = normalized_category in part_category
            matches = matches or (
                normalized_category == "memoria" and "ram" in part_category
            )
            matches = matches or (
                normalized_category in {"ssd", "almacenamiento"}
                and "almacen" in part_category
            )
            matches = matches or (
                normalized_category in {"gpu", "tarjeta de video"}
                and "video" in part_category
            )
            if matches:
                category = str(part["category"])
                break
        if category is None:
            reply = "El armado seleccionado no contiene esa categoría para reemplazar."
            return {"pc_build_selected": True, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        repository = ServiceRepository()
        revised = replace_pc_build_component(
            repository, current_parts=parts, category=category,
            replacement_code=match.group("code"),
        )
        total = Decimal(str(state["build_labor_cost"])) + sum(
            (Decimal(str(part["subtotal"])) for part in revised), Decimal("0.00")
        )
        budget = state.get("build_budget_max")
        if budget is not None and total > Decimal(str(budget)):
            reply = f"El cambio suma {CURRENCY_SYMBOL} {total:.2f}, por encima del tope. No actualicé el armado."
            return {"pc_build_selected": True, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        reply = f"Actualicé la propuesta con el componente vigente. El nuevo total es {CURRENCY_SYMBOL} {total:.2f}."
        return {"pc_build_selected": True, "matched_parts": revised,
                "build_total": total, "response": reply,
                "messages": [AIMessage(content=reply)]}

    intent = str(state.get("build_intended_use", "")).strip()
    if not intent:
        reply = "¿El armado es para juegos, oficina o estudio?"
        return {"pc_build_pending": False, "pc_build_collecting_use": True,
                "response": reply,
                "messages": [AIMessage(content=reply)]}
    if state.get("awaiting_build_selection"):
        options = list(state.get("build_options", []))
        selected = _select_option(latest, options)
        if selected is None:
            reply = "Elige uno de los perfiles enumerados, por número o nombre."
            return {"awaiting_build_selection": True, "response": reply,
                    "messages": [AIMessage(content=reply)]}
    else:
        settings = load_settings()
        labor = settings.labor_price_for("pc_build")
        options = available_pc_builds(
            ServiceRepository(), intended_use=intent, labor_cost=labor,
            budget_max=state.get("build_budget_max"),
        )
        if not options:
            reply = "No encontré un perfil completo con precio positivo y stock suficiente. No reservé productos."
            return {"pc_build_pending": False, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        budget = state.get("build_budget_max")
        fitting = [option for option in options if option["within_budget"]]
        options = fitting if budget is not None and fitting else options
        selected = _select_option(latest, options) if state.get("awaiting_build_selection") else None
        if selected is None:
            lines = [f"{index}. {item['name']}: {CURRENCY_SYMBOL} {item['total']:.2f}"
                     for index, item in enumerate(options, 1)]
            reply = ("Perfiles disponibles con precios y existencias actuales:\n" +
                     "\n".join(lines) + "\nElige uno por número o nombre. La compatibilidad final requiere revisión técnica.")
            return {"pc_build_pending": False, "awaiting_build_selection": True,
                    "build_options": options, "response": reply,
                    "messages": [AIMessage(content=reply)]}

    lines = [f"- {part['name']} ({part['code']}): {CURRENCY_SYMBOL} {part['unit_price']:.2f}"
             for part in selected["parts"]]
    reply = (f"Perfil seleccionado: {selected['name']}\n" + "\n".join(lines) +
             f"\nEnsamble: {CURRENCY_SYMBOL} {selected['labor_cost']:.2f}; total: {CURRENCY_SYMBOL} {selected['total']:.2f}. "
             "Es una propuesta pendiente: no guardé cotización ni reservé stock. Verifica compatibilidad final con un técnico.")
    return {"pc_build_pending": False, "awaiting_build_selection": False,
            "pc_build_selected": True, "selected_build_profile_id": selected["code"],
            "matched_parts": selected["parts"], "build_labor_cost": selected["labor_cost"],
            "build_total": selected["total"], "build_options": options,
            "response": reply, "messages": [AIMessage(content=reply)]}
