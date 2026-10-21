"""Reglas locales para datos comerciales y rutas; sin clientes ni servicios."""
import re
import unicodedata
from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from app.agents.decentralized.data_compat import (
    normalize_handoff_record, normalize_inventory_result, normalize_sales_inventory_item,
)


def normalize_text(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def latest_user_message(state):
    return next((m.content for m in reversed(state["messages"])
                 if isinstance(m, HumanMessage) and isinstance(m.content, str)), "")


def is_compatibility_query(text):
    text = normalize_text(text)
    return any(word in text for word in ("compatib", "sirve para mi", "funciona con mi"))


def classify_support_triage(state):
    """Clasificación conversacional conservadora; nunca confirma una causa."""
    text = normalize_text(latest_user_message(state))
    if re.search(r"\b(que es|que significa|como funciona)\b", text):
        return None
    # Una respuesta breve puede completar una pregunta previa de Soporte.
    # No recuperar una falla antigua ante una solicitud nueva explícita.
    if len(text.split()) <= 6 and not re.search(r"\b(ticket|horario|precio|stock|presencial)\b", text):
        messages = state.get("messages", [])
        previous = next((m for m in reversed(messages[:-1]) if isinstance(m, AIMessage)), None)
        if previous and isinstance(previous.content, str) and "?" in previous.content:
            humans = [m.content for m in messages if isinstance(m, HumanMessage) and isinstance(m.content, str)]
            if len(humans) >= 2 and any(w in normalize_text(previous.content) for w in ("aplicacion", "sistema operativo", "mensaje de error")):
                text = normalize_text(humans[-2]) + ". " + text
    hardware = software = False
    clauses = re.split(r"[.!?;,\n]|\b(?:pero|aunque|y)\b", text)
    for clause in clauses:
        if re.search(r"\b(quizas|podria|hipoteticamente|si|creo)\b", clause):
            continue
        # "no enciende" describe una falla; "no quiero cambiar" niega una petición.
        negation_text = re.sub(r"\bno (enciende|arranca|abre|funciona)\b", "falla", clause)
        if re.search(r"\b(no|nunca|tampoco|sin|descarto)\b", negation_text):
            continue
        hardware |= bool(re.search(r"\b(no enciende|sale humo|olor a quemado|bateria (?:esta )?hinchada|se recalienta|sobrecalentamiento|temperatura alta)\b", clause)
                         or re.search(r"\b(reemplazar|cambiar|falla|averiado|roto)\b.*\b(ssd|ram|fuente|pantalla|bateria|componente)\b", clause))
        software |= bool(re.search(r"\b(aplicacion|programa|editor|navegador)\b.*\b(se cierra|falla|error|no abre)\b", clause)
                         or re.search(r"\b(instalar|actualizar|configurar|configuracion)\b.*\b(windows|linux|ubuntu|macos|controlador|controladores|driver|drivers|aplicacion|programa)\b", clause)
                         or re.search(r"\b(controlador|driver)\b.*\b(error|falla)\b", clause))
    if hardware:
        return "tecnico"
    if software:
        return "software"
    if re.search(r"\b(lento|lentitud|pantalla azul|no enciende|sistema operativo|windows|aplicacion|controlador|driver|humo|ram|ssd)\b", text):
        return "aclarar"
    return None


def is_diagnostic_pricing_query(text):
    text = normalize_text(text)
    return (any(w in text for w in ("revision", "diagnostico"))
            and any(w in text for w in ("cuanto", "precio", "costo", "cuesta", "cotiza")))


def is_handoff_without_progress(state, origin, destination):
    """Consulta el mismo token de auditoría sin modificar registros ni límites."""
    from app.agents.decentralized.handoffs import progress_token
    try:
        records = [normalize_handoff_record(record) for record in state.get("handoff_records", [])]
    except (ValueError, TypeError):
        return True
    token = progress_token(state)
    return any(record.get("origin") == origin and record.get("destination") == destination
               and record.get("request_revision") == state.get("request_revision")
               and record.get("progress_token") == token
               for record in records)


def has_reported_physical_hazard(text):
    """Indicios de peligro afirmados; una negación no demuestra peligro."""
    return any(re.search(r"\b(sale humo|olor a quemado|bateria (?:esta )?hinchada)\b", clause)
               and not re.search(r"\b(no|nunca|sin|tampoco|quizas|podria|si|creo)\b", clause)
               for clause in re.split(r"[.!?;,\n]|\b(?:pero|aunque|y)\b", normalize_text(text)))


def is_customer_service_query(text):
    return bool(re.search(r"\b(citas?|presencial|horarios?|direccion|contacto|contactar)\b", normalize_text(text)))


def cannot_perform_checks(text):
    text = normalize_text(text)
    return any(w in text for w in ("no se hacer", "no se conectar", "no sabria", "ni idea", "no puedo hacer", "no se realizar"))


def is_inventory_query(text):
    text = normalize_text(text)
    return any(w in text for w in ("stock", "dispon", "existencias", "que ssd tienes"))


def contains_placeholder(text):
    text = normalize_text(text)
    return "[" in text or "]" in text or "nombre exacto del" in text


def extract_inventory_reference(text):
    """Solo extrae una referencia SSD explícita; nunca completa capacidad/interfaz."""
    if contains_placeholder(text):
        return None
    match = re.search(r"\bssd\s*\d+\s*(?:gb|tb)(?:\s+(?:nvme|sata|m\.?2))?", text, re.I)
    return match[0].strip() if match else None


def handoff(agent, tool_name, **args):
    return {"current_agent": agent, "messages": [AIMessage(content="", tool_calls=[
        {"name": tool_name, "args": args, "id": f"handoff-{uuid4().hex}"}
    ])]}


def is_part_reference_confirmed(state, name):
    """Exige identificación específica aportada por el usuario, no por el modelo."""
    if not isinstance(name, str):
        return False
    normalized = normalize_text(name).strip()
    if normalized in {"ssd", "disco", "disco ssd", "ram", "bateria", "pantalla", "fuente", "cargador"}:
        return False
    compact = re.sub(r"\W+", "", normalized)
    return bool(compact) and any(
        compact in re.sub(r"\W+", "", normalize_text(m.content))
        for m in state["messages"] if isinstance(m, HumanMessage) and isinstance(m.content, str)
    )


CUSTOMER_SERVICE_UNAVAILABLE = (
    "No puedo reservar citas, registrar visitas ni confirmar que alguien te contactará desde este chat. "
    "No tengo canales, dirección ni horarios de atención verificados para indicarte cómo solicitar una visita. "
    "La revisión presencial es una recomendación; todavía no hay una reserva ni una solicitud registrada."
)


ATENCION_NO_CONFIGURADA = CUSTOMER_SERVICE_UNAVAILABLE


def build_verified_quote(inventory, errors, pending=False, scope=None):
    """Mano de obra sin tarifa oficial: nunca producir total ni importe inventado."""
    quote = {"currency": "PEN", "status": "incomplete", "parts": [],
             "labor_total": None, "total": None, "known_parts_subtotal": None}
    if scope == "solo_servicio":
        return quote, "La tarifa de revisión o mano de obra está pendiente de validación. No puedo confirmar un precio. No incluye repuestos."
    if errors or pending:
        return quote, "No puedo confirmar disponibilidad ni precios: el inventario sigue pendiente o tiene errores."
    if not inventory:
        return quote, "No hay resultados de inventario verificados. La tarifa de mano de obra está pendiente; no puedo confirmar un total."
    try:
        inventory = [normalize_sales_inventory_item(item) for item in inventory]
    except (ValueError, TypeError):
        return quote, "No puedo confirmar disponibilidad ni precios: el inventario sigue pendiente o tiene errores."
    lines = ["Cotización preliminar de repuestos (PEN):"]
    subtotal = Decimal("0.00")
    seen = set()
    for item in inventory:
        key = (item["name"], item["quantity"])
        if key in seen:
            continue
        seen.add(key)
        if not item.get("found", True):
            lines.append(f"{item['name']}: no se encontró una referencia única coincidente. Confirma la capacidad, interfaz y nombre; no sustituiré el repuesto por otro.")
            continue
        price = Decimal(item["unit_price"]).quantize(Decimal("0.01"))
        amount = (price * item["quantity"]).quantize(Decimal("0.01")) if item["available"] else None
        quote["parts"].append({"name": item["name"], "quantity": item["quantity"],
                               "stock": item["stock"], "unit_price": str(price),
                               "available": item["available"], "subtotal": str(amount) if amount is not None else None})
        lines.append(f"{item['name']}: cantidad solicitada {item['quantity']}; stock {item['stock']}; "
                     f"precio unitario S/ {price}; " + (f"subtotal S/ {amount}." if amount is not None else "stock insuficiente."))
        if amount is not None:
            subtotal += amount
    if quote["parts"]:
        quote["known_parts_subtotal"] = str(subtotal)
        lines.append(f"Subtotal de repuestos disponibles: S/ {subtotal}.")
    lines.extend([
                  "Instalación y mano de obra no incluidas: tarifa pendiente de validación. No hay un total final.",
                  "Disponibilidad no confirma compatibilidad. No se ha reservado stock ni confirmado una compra."])
    return quote, "\n".join(lines)


def is_software_commercially_eligible(state):
    """Elegibilidad conversacional; no certifica diagnóstico, precio ni ejecución."""
    assessment = state.get("technical_assessment", {})
    if not isinstance(assessment, dict):
        return False
    user = normalize_text(latest_user_message(state))
    diagnosis = assessment.get("software_diagnosis")
    revision = state.get("request_revision")
    # TechnicalAssessment no contiene revisión ni estado de resolución por área.
    # Una revisión global no fecha el diagnóstico: exigir reconfirmación actual
    # de su texto exacto y no interpretar un registro Hardware como ya resuelto.
    clauses = re.split(r"[.!?;\n,]|\b(?:pero|aunque|sin embargo|y)\b", user)
    def affirmative(clause):
        return not re.search(r"\b(no|nunca|jamas|sin|tampoco|descartado|descarto|quizas|podria|si)\b",
                             clause.replace("sin repuestos", ""))
    return (
        isinstance(diagnosis, str) and bool(diagnosis.strip())
        and type(revision) is int and revision >= 0
        and any(re.search(r"\bconfirmo\b", clause)
                and normalize_text(diagnosis.strip()) in clause and affirmative(clause)
                for clause in clauses)
        and not assessment.get("uncertainties")
        and not assessment.get("compatibility_pending")
        and not state.get("required_parts")
        and not state.get("requested_items")
        and not assessment.get("hardware_diagnosis")
        and any(re.search(r"\b(precio|cotiza|cotizar|costo|cuanto)\b", clause)
                and affirmative(clause) for clause in clauses)
        and any(any(term in clause for term in ("sin repuestos", "solo servicio", "solo diagnostico"))
                and affirmative(clause) for clause in clauses)
    )


def current_inventory_results(state, required=None):
    """Reutiliza únicamente resultados de la revisión y requerimiento actuales."""
    revision = state.get("request_revision", 0)
    if (type(revision) is not int or revision < 0
            or type(state.get("inventory_revision")) is not int
            or state["inventory_revision"] != revision):
        return []
    required = state.get("required_parts", []) if required is None else required
    try:
        results = [normalize_inventory_result(item) for item in state.get("inventory_results", [])]
    except TypeError:
        return []
    return [item for item in results
            if any(item.get("requested_name") == part.get("name")
                   and item.get("quantity") == part.get("quantity") for part in required)]


def prepare_inventory_request(state, required):
    """Cada requerimiento comercial retorna a Ventas; conserva coincidencias vigentes."""
    revision = state.get("request_revision", 0)
    if type(revision) is not int or revision < 0:
        raise ValueError("Revisión de inventario inválida")
    results = current_inventory_results(state, required)
    complete = bool(required) and all(any(item.get("requested_name") == part["name"]
                                         and item.get("quantity") == part["quantity"]
                                         for item in results) for part in required)
    return {"request_revision": revision, "required_parts": required,
            "inventory_results": results, "inventory_revision": revision if results else None,
            "inventory_pending": not complete, "inventory_requested_by": "ventas"}


def evaluate_supply(state):
    """Disponibilidad local verificada; ausencia/ambigüedad nunca es stock cero."""
    checks, missing = [], []
    parts = state.get("required_parts", [])
    if not isinstance(parts, list) or any(not isinstance(part, dict) for part in parts):
        return {"inventory_checks": [], "out_of_stock_items": [], "destination": None}
    raw = state.get("inventory_results", [])
    results = current_inventory_results(state) if isinstance(raw, list) and all(isinstance(item, dict) for item in raw) else []
    valid = bool(parts) and not any("inventario" in str(error).lower() for error in state.get("errors", []))
    for part in parts:
        matches = [item for item in results if item.get("requested_name") == part.get("name")
                   and item.get("quantity") == part.get("quantity")]
        result = matches[0] if len(matches) == 1 else None
        status, shortage, fields = "NEEDS_DETAILS", None, []
        if (not isinstance(part.get("name"), str) or not part["name"].strip()
                or type(part.get("quantity")) is not int or part["quantity"] <= 0):
            fields = ["referencia y cantidad positiva verificadas"]
            valid = False
        elif result is None:
            fields = ["consulta vigente"]
            valid = False
        elif type(result.get("quantity")) is not int or result["quantity"] <= 0:
            fields = ["cantidad verificada"]
            valid = False
        elif result.get("found") is False:
            status = "NEEDS_DETAILS" if result.get("match_status") == "ambiguous" else "NOT_FOUND"
            fields = ["identificación de catálogo"]
            valid = False
        elif (result.get("found") is not True
              or not isinstance(result.get("name"), str) or not result["name"].strip()
              or result.get("match_status") in {"ambiguous", "not_found"}
              or type(result.get("stock")) is not int or result["stock"] < 0
              or type(result.get("available")) is not bool
              or result["available"] != (result["stock"] >= part["quantity"])):
            fields = ["referencia y existencias coherentes confirmadas"]
            valid = False
        elif result["available"]:
            status, shortage = "AVAILABLE", 0
        elif (result.get("found") is True and type(result.get("stock")) is int
              and result["stock"] >= 0 and result["stock"] < part["quantity"]):
            shortage = part["quantity"] - result["stock"]
            status = "PARTIAL" if result["stock"] else "OUT_OF_STOCK"
            missing.append({**part, "quantity": shortage})
        else:
            fields = ["existencias confirmadas"]
            valid = False
        checks.append({"status": status, "request": dict(part), "candidates": [],
                       "missing_quantity": shortage, "missing_fields": fields})
    return {"inventory_checks": checks, "out_of_stock_items": missing,
            "destination": ("compras" if missing else "ventas") if valid else None}

def build_supply_handoff(state):
    evaluation = evaluate_supply(state)
    destination = evaluation.pop("destination")
    if destination is None:
        update = {"current_agent": "almacen", "messages": [AIMessage(content="Falta una identificación o consulta vigente fiable. Confirma la referencia exacta; no puedo interpretar ausencia o ambigüedad como stock agotado.")]}
    else:
        update = handoff("almacen", {"ventas": "transfer_to_sales", "compras": "transfer_to_purchasing"}[destination], reason="Faltantes confirmados" if destination == "compras" else "Inventario vigente verificado")
    update.update(evaluation, inventory_query=None)
    return update

normalizar = normalize_text
ultimo_usuario = latest_user_message
es_compatibilidad = is_compatibility_query
triaje_soporte = classify_support_triage
es_revision_comercial = is_diagnostic_pricing_query
transferencia_sin_progreso = is_handoff_without_progress
peligro_fisico_reportado = has_reported_physical_hazard
es_atencion = is_customer_service_query
no_puede_probar = cannot_perform_checks
es_inventario = is_inventory_query
es_marcador = contains_placeholder
nombre_inventario = extract_inventory_reference
repuesto_confirmado = is_part_reference_confirmed
cotizacion_verificada = build_verified_quote
software_comercial_elegible = is_software_commercially_eligible
inventario_vigente = current_inventory_results
preparar_inventario = prepare_inventory_request
evaluar_abastecimiento = evaluate_supply
salida_abastecimiento = build_supply_handoff
