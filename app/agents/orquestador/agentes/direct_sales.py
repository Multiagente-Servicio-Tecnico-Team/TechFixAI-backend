"""Standalone product-sale quotes for the supervisor chat graph."""

import re
from decimal import Decimal

from langchain_core.messages import AIMessage, HumanMessage

from app.application.catalog import CatalogService
from app.application.chat_sales_quotes import save_chat_sales_quote
from app.database.repository import ServiceRepository


def _latest_user(state: dict) -> str:
    return next((str(message.content).strip() for message in reversed(state.get("messages", []))
                 if isinstance(message, HumanMessage)), "")


def direct_sales_node(state: dict) -> dict[str, object]:
    product = str(state.get("direct_sale_product") or "").strip()
    quantity = state.get("direct_sale_quantity")
    if not product:
        reply = "¿Qué producto quieres comprar? Indica el artículo y, si lo sabes, capacidad, marca o interfaz."
        return {"direct_sale_pending": True, "response": reply, "messages": [AIMessage(content=reply)]}
    if type(quantity) is not int or quantity < 1:
        reply = f"¿Cuántas unidades de «{product}» necesitas?"
        return {"direct_sale_pending": True, "response": reply, "messages": [AIMessage(content=reply)]}
    if quantity > 100:
        reply = "Para esta cotización indica una cantidad entre 1 y 100 unidades."
        return {"direct_sale_pending": True, "response": reply, "messages": [AIMessage(content=reply)]}

    catalog = CatalogService(ServiceRepository())
    selected_candidates = list(state.get("direct_sale_candidates") or [])
    latest = _latest_user(state)
    if selected_candidates:
        normalized = " ".join(latest.casefold().split())
        index_match = re.fullmatch(r"(?:opcion|articulo|el)?\s*(\d{1,2})", normalized)
        selected = None
        if index_match:
            index = int(index_match[1]) - 1
            if 0 <= index < len(selected_candidates):
                selected = selected_candidates[index]
        if selected is None:
            matches = [candidate for candidate in selected_candidates
                       if normalized in {str(candidate.get("code", "")).casefold(),
                                         str(candidate.get("name", "")).casefold()}]
            if len(matches) == 1:
                selected = matches[0]
        if selected is None:
            reply = "Elige una opción por número, código o nombre exacto. Todavía no se creó una cotización."
            return {"direct_sale_pending": True, "direct_sale_candidates": selected_candidates,
                    "response": reply, "messages": [AIMessage(content=reply)]}
        product = str(selected.get("code") or selected["name"])

    result = catalog.lookup(product, quantity)
    if result.get("found") is not True:
        candidates = result.get("candidates", [])
        if candidates:
            lines = [f"{index}. {row.get('code') or row['id']}: {row['name']} — S/ {row['unit_price']} c/u; stock {row['current_stock']}"
                     for index, row in enumerate(candidates, 1)]
            reply = ("Encontré varias coincidencias. Elige una para volver a verificar su precio y stock:\n"
                     + "\n".join(lines))
            return {"direct_sale_pending": True, "direct_sale_product": product,
                    "direct_sale_quantity": quantity, "direct_sale_candidates": candidates,
                    "response": reply, "messages": [AIMessage(content=reply)]}
        reply = f"No encontré «{product}» en el catálogo. Prueba con un nombre o código más específico."
        return {"direct_sale_pending": True, "direct_sale_product": product,
                "direct_sale_quantity": quantity, "direct_sale_candidates": [],
                "response": reply, "messages": [AIMessage(content=reply)]}
    if not result.get("available"):
        reply = (f"El catálogo encontró {result['name']}, pero solo hay {result['stock']} unidades y solicitas {quantity}. "
                 "No he creado una cotización ni reservado stock.")
        return {"direct_sale_pending": False, "direct_sale_candidates": [],
                "response": reply, "messages": [AIMessage(content=reply)]}

    item_id = result.get("inventory_id")
    if type(item_id) is not int or item_id < 1:
        reply = "No pude verificar el identificador del artículo; no se creó una cotización."
        return {"direct_sale_pending": False, "response": reply, "messages": [AIMessage(content=reply)]}
    try:
        saved = save_chat_sales_quote(
            customer_id=int(state["user_id"]), quote_type="DIRECT_SALE",
            parts=[{"inventory_id": item_id, "name": result["name"], "code": result.get("code"),
                    "quantity": quantity, "unit_price": Decimal(str(result["unit_price"])),
                    "subtotal": Decimal(str(result["unit_price"])) * quantity}],
            labor_cost="0.00", observations="Cotización de venta directa preparada desde el chat del Orquestador.",
        )
    except (ValueError, LookupError, RuntimeError):
        reply = "El precio o stock cambió antes de guardar la cotización. No se creó ningún registro; vuelve a consultar el artículo."
        return {"direct_sale_pending": False, "response": reply, "messages": [AIMessage(content=reply)]}

    part = saved["parts"][0]
    total = Decimal(str(saved["total_amount"]))
    reply = (f"Cotización de venta #{saved['id']} guardada, sin ticket de servicio y sin reserva todavía:\n"
             f"- {part['name']} × {part['quantity']}: S/ {part['subtotal']}\n"
             f"Total: S/ {total}. Responde **Sí, confirmo** para reservar el stock o **No** para rechazarla.")
    return {
        "direct_sale_pending": False,
        "direct_sale_candidates": [],
        "sales_quote_id": saved["id"],
        "sales_quote_status": "PENDING",
        "sales_quote_kind": "DIRECT_SALE",
        "sales_payment_code": None,
        "awaiting_sales_quote_confirmation": True,
        "matched_parts": saved["parts"],
        "build_labor_cost": Decimal("0.00"),
        "build_total": total,
        "response": reply,
        "messages": [AIMessage(content=reply)],
    }
