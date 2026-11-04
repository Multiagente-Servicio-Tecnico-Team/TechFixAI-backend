"""Nodo contable descentralizado: guía manual sin escrituras ni borradores."""
import re
from datetime import date

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from app.agents.decentralized.policies.policy import latest_user_message
from app.application.accounting_assistant import AccountingAssistant
from app.application.errors import AccountingError
from app.domain.accounting import AccountingValidationError


def _filters(message: str) -> dict:
    result = {}
    allowed = {"from_date", "to_date", "category_id", "status", "entry_number", "limit", "offset"}
    for key in re.findall(r"\b([a-z_]+)=\S+", message):
        if key not in allowed:
            raise AccountingValidationError("Filtro contable no admitido.")
    for match in re.finditer(r"\b(from_date|to_date|category_id|status|entry_number|limit|offset)=([^\s]+)", message):
        key, value = match.groups()
        try:
            result[key] = (date.fromisoformat(value) if key.endswith("date") else value if key == "status" else int(value))
        except ValueError:
            raise AccountingValidationError(f"El filtro {key} no es válido.") from None
    return result


def _reply_for_request(message: str, assistant: AccountingAssistant) -> str:
    normalized = message.casefold()
    if "categor" in normalized:
        categories = assistant.list_categories()
        if not categories:
            return "No hay categorías contables activas."
        return "Categorías contables: " + "; ".join(
            f"{item['id']}: {item['name']} ({item['code']})" for item in categories)
    reversal = re.search(r"revertir asiento\s+(\d+)\s+fecha=(\d{4}-\d{2}-\d{2})\s+motivo=(.+)$", message, re.I)
    if reversal:
        request = assistant.prepare_reversal(entry_id=int(reversal[1]),
                                             operation_date=date.fromisoformat(reversal[2]), reason=reversal[3])
        return (f"Solicitud de reversión del asiento {request['entry_id']} preparada para {request['operation_date']}. "
                "El chat no ejecuta la reversión; ADMIN debe confirmarla mediante el POST de 003.")
    if "revert" in normalized or "revers" in normalized:
        return "Para solicitar reversión indica: revertir asiento ID fecha=AAAA-MM-DD motivo=RAZÓN. La ejecución requiere confirmación mediante la API 003."
    detail = re.search(r"\b(?:detalle\s+(?:del\s+)?|ver\s+)?asiento\s+(\d+)\b", message, re.I)
    if detail:
        entry = assistant.get_entry(int(detail[1]))
        lines = entry.get("lines", [])
        return (f"Asiento {entry['id']}, estado {entry['status']}, fecha {entry['operation_date']}, "
                f"concepto {entry['concept']}, detalle {entry['detail']}, debe {entry['debit_total']} "
                f"y haber {entry['credit_total']} {entry['currency']}. "
                + "Líneas: " + "; ".join(
                    f"{line['account_code']} {line['account_name']}: debe {line['debit']}, haber {line['credit']}"
                    for line in lines))
    if "asiento" in normalized:
        result = assistant.list_entries(**_filters(message))
        items = result.get("items", [])
        if not items:
            return "No hay asientos para esos filtros."
        return (f"Asientos {len(items)} de {result['total']}: " + "; ".join(
            f"{item['id']} ({item['status']}, {item['operation_date']}, {item['concept']})" for item in items))
    return ("Puedo consultar categorías, listar asientos con filtros de 003, ver un asiento por ID y preparar "
            "una solicitud de reversión con fecha y motivo. La creación de asientos requiere la API 003 y confirmación de ADMIN.")


def accountant_node(state, runtime: Runtime):
    context = runtime.context or {}
    if context.get("authenticated_role") != "ADMIN":
        return {"current_agent": "soporte", "messages": [AIMessage(content="La operación contable requiere una sesión ADMIN.")]}
    message = latest_user_message(state).strip()
    if message.casefold() in {"salir", "volver", "terminar"}:
        return {"current_agent": "soporte", "messages": [AIMessage(content="Volvemos a la atención general.")]}
    factory = context.get("accounting_service_factory")
    if factory is None:
        return {"current_agent": "contador", "messages": [AIMessage(content="El servicio contable no está disponible.")]}
    try:
        reply = _reply_for_request(message, AccountingAssistant(factory(), authenticated_role=context["authenticated_role"]))
    except (AccountingError, AccountingValidationError, KeyError, TypeError, ValueError):
        reply = "No se pudo completar la consulta contable. Revisa el ID, los filtros, la fecha y el motivo."
    return {"current_agent": "contador", "messages": [AIMessage(content=reply)]}
