"""Contratos de transferencia locales; no seleccionan un supervisor ni ejecutan agentes."""
import hashlib
import json
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from app.agents.decentralized.data_compat import (
    normalize_handoff_payload, normalize_handoff_record,
)


ALLOWED_HANDOFFS = {
    "soporte": frozenset({"tecnico", "software", "ventas", "garantia", "logistica", "facturacion"}),
    "ventas": frozenset({"tecnico", "software", "almacen", "facturacion", "soporte"}),
    "tecnico": frozenset({"software", "almacen", "ventas", "logistica", "garantia", "soporte"}),
    "software": frozenset({"tecnico", "almacen", "ventas", "logistica", "garantia", "soporte"}),
    "almacen": frozenset({"tecnico", "software", "ventas", "compras"}),
    "compras": frozenset({"ventas"}),
    "facturacion": frozenset({"ventas", "logistica", "soporte"}),
    "logistica": frozenset({"garantia", "soporte"}),
    "garantia": frozenset({"logistica", "tecnico", "software", "facturacion", "soporte"}),
}
HANDOFF_TOOLS = {f"transferir_a_{agent}": agent for agent in ALLOWED_HANDOFFS}
HANDOFF_TOOLS["solicitar_inventario"] = "almacen"


class HandoffRecord(TypedDict):
    origin: str
    destination: str
    reason: str
    request_revision: int | None
    progress_token: str


def validate_handoff(origin, destination, reason, available_agents, revision=None):
    if origin not in ALLOWED_HANDOFFS or destination not in ALLOWED_HANDOFFS:
        raise ValueError("Agente de transferencia desconocido")
    if origin == destination:
        raise ValueError("Transferencia al mismo agente")
    if destination not in ALLOWED_HANDOFFS[origin]:
        raise ValueError("Transferencia no permitida")
    if origin not in available_agents or destination not in available_agents:
        raise ValueError("Agente de transferencia no disponible")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Motivo de transferencia obligatorio")
    if revision is not None and (type(revision) is not int or revision < 0):
        raise ValueError("Revisión de transferencia inválida")


def selected_handoff(messages):
    """Primer handoff exitoso del lote final, compartido por todos los lectores."""
    results = []
    for result in reversed(messages):
        if not isinstance(result, ToolMessage):
            break
        results.append(result)
    return next((result for result in reversed(results)
                 if result.status != "error" and result.name in HANDOFF_TOOLS), None)


def handoff_reason(messages):
    """Lee argumentos de la transferencia seleccionada y admite resultados legacy."""
    result = selected_handoff(messages)
    if result is None:
        return None
    try:
        data = json.loads(result.content)
    except (ValueError, TypeError):
        data = None
        legacy_reason = result.content.partition(":")[2].strip() if ":" in result.content else result.content
    else:
        legacy_reason = None
    if isinstance(data, dict):
        try:
            data = normalize_handoff_payload(data)
        except (ValueError, TypeError):
            return None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["id"] == result.tool_call_id and call["name"] == result.name:
                    try:
                        args = normalize_handoff_payload(call["args"])
                    except (ValueError, TypeError):
                        return None
                    if result.name == "solicitar_inventario":
                        query = args.get("query")
                        return "Consultar inventario" if isinstance(query, str) and query.strip() else None
                    return args.get("reason")
    if isinstance(data, dict):
        return ("Consultar inventario" if result.name == "solicitar_inventario"
                and isinstance(data.get("query"), str) and data["query"].strip()
                else data.get("reason"))
    return legacy_reason


def canonical_content(content):
    """El formato JSON no constituye evidencia nueva."""
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        return content


def progress_token(state):
    """Compara evidencia sin guardar mensajes/entradas completas en el registro.

    IDs de llamadas y textos de handoff no constituyen progreso. Este token es
    interno, no un dato destinado a trazas; no demuestra veracidad de evidencia.
    """
    evidence = []
    for message in state.get("messages", [])[state.get("turn_start_index", 0):]:
        if isinstance(message, HumanMessage):
            evidence.append(("human", message.content))
        elif isinstance(message, ToolMessage) and message.name not in HANDOFF_TOOLS and message.status != "error":
            evidence.append((message.name, canonical_content(message.content)))
    business = {key: state.get(key) for key in (
        "required_parts", "requested_items", "selected_items", "technical_assessment",
        "inventory_pending", "quote_scope", "proposal", "ticket_id", "quote_id",
        "payment_id", "logistics_record_id", "warranty_id", "warranty_claim_id",
    )}
    business["inventory_results"] = sorted({
        json.dumps({key: value for key, value in item.items() if key != "tool_call_id"},
                   sort_keys=True, default=str, ensure_ascii=False)
        for item in state.get("inventory_results", [])
    })
    # Reejecutar una herramienta y recibir el mismo contenido no es evidencia nueva.
    evidence = sorted({json.dumps(item, sort_keys=True, default=str, ensure_ascii=False)
                       for item in evidence})
    return hashlib.sha256(json.dumps([evidence, business], sort_keys=True,
                                    default=str, ensure_ascii=False).encode()).hexdigest()


def make_handoff_record(state, origin, destination, reason, available_agents):
    revision = state.get("request_revision")
    validate_handoff(origin, destination, reason, available_agents, revision)
    records = [normalize_handoff_record(record) for record in state.get("handoff_records", [])]
    token = progress_token(state)
    for record in records:
        if (record["origin"] == origin and record["destination"] == destination
                and record["request_revision"] == revision and record["progress_token"] == token):
            raise ValueError("Transferencia repetida sin información nueva")
    return HandoffRecord(origin=origin, destination=destination, reason=reason.strip(),
                         request_revision=revision, progress_token=token)
