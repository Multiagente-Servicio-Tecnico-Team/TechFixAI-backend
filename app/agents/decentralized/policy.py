"""Reglas locales para datos comerciales y rutas; sin clientes ni servicios."""
import re
import unicodedata
from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage

from app.application.quotes import calculate_quote as calculate_shared_quote


def normalizar(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def ultimo_usuario(state):
    return next((m.content for m in reversed(state["messages"])
                 if isinstance(m, HumanMessage) and isinstance(m.content, str)), "")


def es_compatibilidad(text):
    text = normalizar(text)
    return any(word in text for word in ("compatib", "sirve para mi", "funciona con mi"))


def es_revision_comercial(text):
    text = normalizar(text)
    return (any(w in text for w in ("revision", "diagnostico"))
            and any(w in text for w in ("cuanto", "precio", "costo", "cuesta", "cotiza")))


def es_atencion(text):
    return bool(re.search(r"\b(citas?|presencial|horarios?|direccion|contacto|contactar)\b", normalizar(text)))


def no_puede_probar(text):
    text = normalizar(text)
    return any(w in text for w in ("no se hacer", "no se conectar", "no sabria", "ni idea", "no puedo hacer", "no se realizar"))


def es_inventario(text):
    text = normalizar(text)
    return any(w in text for w in ("stock", "dispon", "existencias", "que ssd tienes"))


def es_marcador(text):
    text = normalizar(text)
    return "[" in text or "]" in text or "nombre exacto del" in text


def nombre_inventario(text):
    """Solo extrae una referencia SSD explícita; nunca completa capacidad/interfaz."""
    if es_marcador(text):
        return None
    match = re.search(r"\bssd\s*\d+\s*(?:gb|tb)(?:\s+(?:nvme|sata|m\.?2))?", text, re.I)
    return match[0].strip() if match else None


def handoff(agent, tool_name, **args):
    return {"current_agent": agent, "messages": [AIMessage(content="", tool_calls=[
        {"name": tool_name, "args": args, "id": f"handoff-{uuid4().hex}"}
    ])]}


def repuesto_confirmado(state, name):
    """Exige identificación específica aportada por el usuario, no por el modelo."""
    if not isinstance(name, str):
        return False
    normalized = normalizar(name).strip()
    if normalized in {"ssd", "disco", "disco ssd", "ram", "bateria", "pantalla", "fuente", "cargador"}:
        return False
    compact = re.sub(r"\W+", "", normalized)
    return bool(compact) and any(
        compact in re.sub(r"\W+", "", normalizar(m.content))
        for m in state["messages"] if isinstance(m, HumanMessage) and isinstance(m.content, str)
    )


ATENCION_NO_CONFIGURADA = (
    "No puedo reservar citas, registrar visitas ni confirmar que alguien te contactará desde este chat. "
    "No tengo canales, dirección ni horarios de atención verificados para indicarte cómo solicitar una visita. "
    "La revisión presencial es una recomendación; todavía no hay una reserva ni una solicitud registrada."
)


def cotizacion_verificada(inventory, errors, pending=False, scope=None):
    """Mano de obra sin tarifa oficial: nunca producir total ni importe inventado."""
    quote = {"currency": "PEN", "status": "incomplete", "parts": [],
             "labor_total": None, "total": None, "known_parts_subtotal": None}
    if scope == "solo_servicio":
        return quote, "La tarifa de revisión o mano de obra está pendiente de validación. No puedo confirmar un precio. No incluye repuestos."
    if errors or pending:
        return quote, "No puedo confirmar disponibilidad ni precios: el inventario sigue pendiente o tiene errores."
    if not inventory:
        return quote, "No hay resultados de inventario verificados. La tarifa de mano de obra está pendiente; no puedo confirmar un total."
    lines = ["Cotización preliminar de repuestos (PEN):"]
    subtotal = Decimal("0.00")
    seen = set()
    for item in inventory:
        key = (item["nombre"], item["cantidad"])
        if key in seen:
            continue
        seen.add(key)
        if not item.get("encontrado", True):
            lines.append(f"{item['nombre']}: no se encontró una referencia única coincidente. Confirma la capacidad, interfaz y nombre; no sustituiré el repuesto por otro.")
            continue
        price = Decimal(item["precio_unitario"]).quantize(Decimal("0.01"))
        amount = None
        if item["disponible"]:
            amount = calculate_shared_quote(
                labor_cost=Decimal("0.00"),
                labor_task_type="sale",
                parts=[{
                    "name": item["nombre"],
                    "quantity": item["cantidad"],
                    "unit_price": price,
                    "current_stock": item["stock"],
                }],
            )["parts"][0]["subtotal"]
        quote["parts"].append({"name": item["nombre"], "quantity": item["cantidad"],
                               "stock": item["stock"], "unit_price": str(price),
                               "available": item["disponible"], "subtotal": str(amount) if amount is not None else None})
        lines.append(f"{item['nombre']}: cantidad solicitada {item['cantidad']}; stock {item['stock']}; "
                     f"precio unitario S/ {price}; " + (f"subtotal S/ {amount}." if amount is not None else "stock insuficiente."))
    if quote["parts"]:
        subtotal = calculate_shared_quote(
            labor_cost=Decimal("0.00"),
            labor_task_type="sale",
            parts=[
                {
                    "name": part["name"],
                    "quantity": part["quantity"],
                    "unit_price": Decimal(part["unit_price"]),
                    "current_stock": part["stock"],
                }
                for part in quote["parts"]
                if part["available"]
            ],
        )["parts_cost"]
        quote["known_parts_subtotal"] = str(subtotal)
        lines.append(f"Subtotal de repuestos disponibles: S/ {subtotal}.")
    lines.extend([
                  "Instalación y mano de obra no incluidas: tarifa pendiente de validación. No hay un total final.",
                  "Disponibilidad no confirma compatibilidad. No se ha reservado stock ni confirmado una compra."])
    return quote, "\n".join(lines)
