"""Conservative, progressive intake. No SQL and no model-controlled identity."""
import re
from decimal import Decimal, InvalidOperation
from langchain_core.messages import AIMessage
from app.agents.decentralized.policy import normalize_text, latest_user_message, classify_support_triage
from app.agents.decentralized.state import invalidate_request
from app.agents.decentralized.ticket_operations import generate_ticket_code, prepare_pending_ticket_operation
from app.database.decentralized_repository import _id, RetryConflict


LABELS = {"equipo": "equipment", "sintomas": "failure_description", "motivo": "failure_description",
          "descripcion": "failure_description", "sistema operativo": "operating_system",
          "producto": "product_description", "cantidad": "quantity", "uso": "intended_use",
          "presupuesto": "budget", "codigo": "warranty_code", "codigo de garantia": "warranty_code",
          "modelo": "model", "marca": "brand", "preferencias": "preferences"}
TYPES = {"REPAIR", "SUPPORT", "SALE", "PC_BUILD", "WARRANTY_CLAIM"}
NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
           "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
SYMPTOMS = ("no enciende", "no arranca", "se apaga", "error", "pantalla azul", "se recalienta")


def natural_fields(text, intent):
    """Extract reported text only; no catalog, compatibility or price inference."""
    fields = {}
    normalized = normalize_text(text)
    if intent in {"REPAIR", "SUPPORT"}:
        equipment = re.search(r"\b(laptop|pc|computadora)\b", normalized)
        if equipment:
            fields["equipment"] = equipment[0]
    if intent in {"REPAIR", "SUPPORT", "WARRANTY_CLAIM"} and any(term in normalized for term in SYMPTOMS):
        fields["failure_description"] = text.strip()
    if intent == "SALE":
        purchase = re.search(r"\bcomprar\s+(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+([^;\n]+)", text, re.I)
        if purchase:
            number = purchase[1].lower()
            quantity = int(number) if number.isdigit() else NUMBERS[number]
            if not 0 < quantity <= 2147483647:
                raise ValueError("Cantidad inválida")
            fields.update(quantity=quantity, product_description=purchase[2].strip())
    return fields


def classify_request(text):
    value = normalize_text(text)
    if any(word in value for word in ("reembolso", "devolver mi pago")):
        return "REFUND"
    if "garantia" in value and any(word in value for word in ("vigente", "vigencia", "vencimiento", "hasta cuando")):
        return "WARRANTY_STATUS_CHECK"
    if any(word in value for word in ("estado del ticket", "seguimiento", "horario", "direccion", "que servicios")):
        return "INFO_QUERY"
    if re.search(r"\b(no quiero|no necesito|no solicito|quizas|tal vez|si quisiera|podria)\b", value):
        return "AMBIGUOUS"
    match = re.search(r"(?:^|[;\n])\s*solicitud:\s*([A-Z_]+)\s*(?:$|[;\n])", text, re.I)
    if match:
        return match[1].upper() if match[1].upper() in TYPES else "AMBIGUOUS"
    if not re.search(r"\b(quiero|quisiera|necesito|solicito|deseo)\b", value):
        if re.search(r"\b(laptop|pc|computadora)\b", value) and any(term in value for term in SYMPTOMS):
            return "REPAIR"
        return None
    if "garantia" in value and any(term in value for term in ("reclamar", "reclamo")):
        return "WARRANTY_CLAIM"
    if any(term in value for term in ("armar", "ensamblar", "pc a medida")):
        return "PC_BUILD"
    if any(term in value for term in ("comprar", "compra directa")):
        return "SALE"
    if any(term in value for term in ("reparar", "reparacion", "mantenimiento")):
        return "REPAIR"
    if any(term in value for term in ("instalar", "configurar", "soporte de software", "controladores")):
        return "SUPPORT"
    if re.search(r"\b(laptop|pc|computadora)\b", value) and any(term in value for term in SYMPTOMS):
        return "REPAIR"
    return None


def capture_ticket_request(state, *, authenticated_customer_id):
    """Return None for legacy informational handling; never infer missing facts.

    Existing prepared work remains immutable. Correction after preparation needs
    reconciliation, as required by invalidate_request(), not a new random code.
    """
    text = latest_user_message(state)
    intent = classify_request(text)
    def reply(content, **patch):
        return {"current_agent": "soporte", "messages": [AIMessage(content=content)], **patch}
    if intent == "AMBIGUOUS":
        return reply("Aclara si solicitas una acción o solo información. No he preparado ni creado un ticket.")
    if intent in {"INFO_QUERY", "WARRANTY_STATUS_CHECK"}:
        return None
    if intent == "REFUND":
        return reply("REFUND no es un tipo de ticket permitido. La ruta administrativa de reembolso no está habilitada; no se preparó un ticket.", intent="REFUND")
    if state.get("ticket_id") is not None:
        return None
    pending = state.get("pending_ticket_operation")
    if pending and (state.get("ticket_correction_required") or re.search(
            r"\b(en lugar|cambia|cambiar|corrige|corregir|ahora|mejor|prefiero)\b", normalize_text(text))):
        return reply("Detecté una corrección. La operación anterior queda bloqueada, con su código intacto, hasta reconciliarla; no se creará otro ticket.", ticket_correction_required=True)
    previous = pending["payload"]["request_type"] if pending else state.get("intent")
    intent = intent or (previous if previous in TYPES else None)
    if intent is None:
        return None
    if authenticated_customer_id is None:
        return reply("Para preparar esta solicitud necesito una sesión autenticada. Puedes continuar consultas informativas sin crear tickets.")
    customer = _id(authenticated_customer_id)
    if state.get("customer_id") != customer:
        raise RetryConflict("Identidad incompatible con Atención")
    intake = dict(state.get("intake") or {})
    patch = {}
    if previous in TYPES and previous != intent:
        patch = invalidate_request(state, new_request=True)
        intake = {}
    fields = natural_fields(text, intent)
    # Answers to the last intake question are data, not new intentions. Never
    # reconcile an already prepared operation by reconstructing its payload.
    missing_before = intake.get("missing_fields", [])
    value = normalize_text(text).strip(" .!¿?¡")
    if not pending and missing_before == ["quantity"]:
        quantity = int(value) if re.fullmatch(r"[1-9]\d*", value) else NUMBERS.get(value)
        if quantity is not None:
            if not 0 < quantity <= 2147483647:
                raise ValueError("Cantidad inválida")
            fields["quantity"] = quantity
    if (not pending and "product_description" in missing_before
            and normalize_text(str(intake.get("product_description", ""))) == "ssd"
            and re.search(r"\b(sata|nvme|\d+\s*(?:gb|tb))\b", value)
            and not re.search(r"\b(no|quizas|tal vez|podria)\b", value)):
        fields["product_description"] = "SSD " + text.strip()
    labelled = set()
    for segment in re.split(r"[;\n]", text):
        label, sep, value = segment.partition(":")
        key = LABELS.get(normalize_text(label.strip()))
        if sep and key:
            value = value.strip()
            if not value:
                return reply("El dato indicado está vacío; precisa su valor antes de preparar la solicitud.")
            if key in {"equipment", "product_description", "warranty_code"} and re.search(r"\b(quizas|tal vez|podria|no se)\b", normalize_text(value)):
                return reply("Ese dato no está confirmado. Precisa la referencia o el equipo sin asumir una hipótesis.")
            if key == "quantity":
                if not re.fullmatch(r"[1-9]\d*", value) or int(value) > 2147483647:
                    return reply("Indica una cantidad entera positiva válida.")
                value = int(value)
            if key == "budget":
                try:
                    value = Decimal(value)
                    if not value.is_finite() or value <= 0:
                        raise ValueError()
                except (InvalidOperation, ValueError):
                    return reply("Indica el presupuesto máximo positivo, sin suponer un precio de catálogo.")
            if key == "preferences":
                value = [value]
            if key in labelled and fields[key] != value:
                return reply("Hay valores contradictorios para el mismo dato; acláralos antes de continuar.")
            fields[key] = value
            labelled.add(key)
    if not intake.get("equipment") and intent in {"REPAIR", "SUPPORT"}:
        equipment = re.search(r"\b(laptop|pc|computadora)\b", normalize_text(text))
        if equipment:
            fields.setdefault("equipment", equipment[0])
    if intent in {"REPAIR", "SUPPORT", "WARRANTY_CLAIM"} and not intake.get("failure_description"):
        if any(term in normalize_text(text) for term in ("no enciende", "no arranca", "se apaga", "error", "pantalla azul")):
            fields.setdefault("failure_description", text.strip())
    changed = any(key in intake and intake[key] != value for key, value in fields.items())
    if pending and not fields and normalize_text(text).strip(" .!¿?¡") not in {"continuar", "continua", "reintentar", "reintento", "si", "confirmo", "ok"}:
        return reply("El mensaje puede cambiar la solicitud preparada. Necesito aclararlo y reconciliarla antes de continuar; su clave permanece intacta.", ticket_correction_required=True)
    if changed and not patch:
        patch = invalidate_request(state)
    intake.update(fields)
    required = {"REPAIR": ["equipment", "failure_description"], "SUPPORT": ["equipment", "failure_description"],
                "SALE": ["product_description", "quantity"], "PC_BUILD": ["intended_use", "budget"],
                "WARRANTY_CLAIM": ["warranty_code", "failure_description"]}[intent]
    missing = [key for key in required if not intake.get(key)]
    if intent == "SALE" and normalize_text(str(intake.get("product_description", ""))).strip() == "ssd":
        if "product_description" not in missing:
            missing.insert(0, "product_description")
    intake["missing_fields"] = missing
    revision = patch.get("request_revision", state.get("request_revision", 0))
    update = {**patch, "customer_id": customer, "intent": intent, "request_type": intent,
              "request_revision": revision, "intake": intake}
    if missing:
        labels = {"equipment":"equipo", "failure_description":"síntomas o motivo", "product_description":"producto y especificaciones",
                  "quantity":"cantidad", "intended_use":"uso principal", "budget":"presupuesto máximo", "warranty_code":"código exacto de garantía"}
        question = ("¿Qué capacidad e interfaz necesitas para la SSD (por ejemplo SATA o NVMe)? No puedo asumir compatibilidad."
                    if missing[0] == "product_description" and intake.get("product_description") else
                    "Indica " + labels[missing[0]] + ". Puedes responder en lenguaje natural o usar una etiqueta si necesitas precisar el dato.")
        return reply(question + " No se ha creado un ticket.", **update)
    description = "\n".join(f"{key}: {value}" for key, value in intake.items() if key not in {"missing_fields", "title"})
    subject = next((str(intake[key]) for key in ("equipment", "product_description", "warranty_code", "intended_use") if intake.get(key)), intent)
    title = f"{intent}: {subject}"[:200]
    code = None if pending else generate_ticket_code()
    update.update(prepare_pending_ticket_operation({**state, **update}, authenticated_customer_id=customer,
        intent=intent, title=title, failure_description=description, code=code))
    update["next_agent"] = {"SALE":"ventas", "PC_BUILD":"ventas", "WARRANTY_CLAIM":"garantia",
                            "SUPPORT":"software", "REPAIR":"software" if classify_support_triage(state)=="software" else "tecnico"}[intent]
    return reply("Solicitud preparada con código estable, pendiente de la futura creación en PostgreSQL. No se ha creado ningún ticket ni transferido una operación persistida.", **update)
