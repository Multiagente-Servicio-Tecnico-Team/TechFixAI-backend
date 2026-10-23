import json
from app.agents.decentralized.data_compat import (
    normalize_handoff_history_entry, normalize_handoff_payload, normalize_inventory_result,
)
from app.agents.decentralized.warranty import warranty_node, garantia_node, warranty_tools, garantia_tools
from app.agents.decentralized.warranty_operations import validate_pending_warranty_operation
from app.agents.decentralized.policy import handoff

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import is_part_reference_confirmed, is_software_commercially_eligible
from app.agents.decentralized.policy import current_inventory_results, prepare_inventory_request
from app.agents.decentralized.policy import evaluate_supply
from app.agents.decentralized.handoffs import (
    HANDOFF_TOOLS, handoff_reason, validate_handoff, make_handoff_record, selected_handoff,
)
from app.agents.decentralized.support import support_node, soporte_node, support_tools, soporte_tools
from app.agents.decentralized.hardware import hardware_node, tecnico_node, hardware_tools, tecnico_tools
from app.agents.decentralized.sales import sales_node, ventas_node, sales_tools, ventas_tools
from app.agents.decentralized.warehouse import warehouse_node, almacen_node, warehouse_tools, almacen_tools
from app.agents.decentralized.tools.almacen_tools import consultar_inventario
from app.agents.decentralized.software import software_node, software_tools
from app.agents.decentralized.purchasing import purchasing_node, compras_node, purchasing_tools, compras_tools
from app.agents.decentralized.tools.compras_tools import consultar_fuentes_abastecimiento
from app.agents.decentralized.tools.tecnico_tools import diagnosticar_problema
from app.agents.decentralized.billing import billing_node, facturacion_node, billing_tools, facturacion_tools
from app.agents.decentralized.tools.facturacion_tools import consultar_capacidades_financieras
from app.agents.decentralized.logistics import logistics_node, logistica_node, logistics_tools, logistica_tools
from app.agents.decentralized.logistics_operations import validate_pending_logistics_operation
from app.agents.decentralized.payment_operations import validate_pending_payment_operation
from langgraph.runtime import Runtime
from typing_extensions import TypedDict


class FinancialContext(TypedDict, total=False):
    authenticated_customer_id: int
    quote_action: str
    quote_proposal_id: str
    quote_conversation_id: str

MAX_HANDOFFS = 5
MAX_TOOL_ITERATIONS = 6

_INITIAL_PURCHASING_TOOLS = purchasing_tools


def _resolve_purchasing_tools():
    if purchasing_tools is compras_tools:
        return purchasing_tools
    if purchasing_tools is _INITIAL_PURCHASING_TOOLS:
        return compras_tools
    if compras_tools is _INITIAL_PURCHASING_TOOLS:
        return purchasing_tools
    raise ValueError("Conflicting purchasing tool registries")


_INITIAL_BILLING_TOOLS = billing_tools
_INITIAL_LOGISTICS_TOOLS = logistics_tools


def _resolve_billing_tools():
    if billing_tools is facturacion_tools:
        return billing_tools
    if billing_tools is _INITIAL_BILLING_TOOLS:
        return facturacion_tools
    if facturacion_tools is _INITIAL_BILLING_TOOLS:
        return billing_tools
    raise ValueError("Conflicting billing tool registries")


def _resolve_logistics_tools():
    if logistics_tools is logistica_tools:
        return logistics_tools
    if logistics_tools is _INITIAL_LOGISTICS_TOOLS:
        return logistica_tools
    if logistica_tools is _INITIAL_LOGISTICS_TOOLS:
        return logistics_tools
    raise ValueError("Conflicting logistics tool registries")


_INITIAL_WARRANTY_TOOLS = warranty_tools


def _resolve_warranty_tools():
    if warranty_tools is garantia_tools:
        return warranty_tools
    if warranty_tools is _INITIAL_WARRANTY_TOOLS:
        return garantia_tools
    if garantia_tools is _INITIAL_WARRANTY_TOOLS:
        return warranty_tools
    raise ValueError("Conflicting warranty tool registries")


_INITIAL_SUPPORT_TOOLS = support_tools
_INITIAL_HARDWARE_TOOLS = hardware_tools


def _resolve_support_tools():
    if support_tools is soporte_tools:
        return support_tools
    if support_tools is _INITIAL_SUPPORT_TOOLS:
        return soporte_tools
    if soporte_tools is _INITIAL_SUPPORT_TOOLS:
        return support_tools
    raise ValueError("Conflicting support tool registries")


def _resolve_hardware_tools():
    if hardware_tools is tecnico_tools:
        return hardware_tools
    if hardware_tools is _INITIAL_HARDWARE_TOOLS:
        return tecnico_tools
    if tecnico_tools is _INITIAL_HARDWARE_TOOLS:
        return hardware_tools
    raise ValueError("Conflicting hardware tool registries")


_INITIAL_SALES_TOOLS = sales_tools
_INITIAL_WAREHOUSE_TOOLS = warehouse_tools


def _resolve_sales_tools():
    if sales_tools is ventas_tools:
        return sales_tools
    if sales_tools is _INITIAL_SALES_TOOLS:
        return ventas_tools
    if ventas_tools is _INITIAL_SALES_TOOLS:
        return sales_tools
    raise ValueError("Conflicting sales tool registries")


def _resolve_warehouse_tools():
    if warehouse_tools is almacen_tools:
        return warehouse_tools
    if warehouse_tools is _INITIAL_WAREHOUSE_TOOLS:
        return almacen_tools
    if almacen_tools is _INITIAL_WAREHOUSE_TOOLS:
        return warehouse_tools
    raise ValueError("Conflicting warehouse tool registries")


AGENT_NODES = {
    "soporte": support_node, "tecnico": hardware_node,
    "ventas": sales_node, "almacen": warehouse_node,
    "software": software_node,
    "compras": purchasing_node,
    "facturacion": billing_node,
    "logistica": logistics_node,
    "garantia": warranty_node,
}


def detect_handoff(messages):
    """Identifica la primera transferencia exitosa del lote final."""
    result = selected_handoff(messages)
    return HANDOFF_TOOLS[result.name] if result is not None else None


def extract_part_handoff(messages):
    """Valida los datos estructurados de transferir_a_almacen."""
    for message in [selected_handoff(messages)]:
        if message is None or message.name not in {"transferir_a_almacen", "transfer_to_warehouse"}:
            return None
        if message.status == "error":
            return None
        try:
            data = json.loads(message.content)
            if isinstance(data, dict):
                data = normalize_handoff_payload(data)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        if data.get("action") != "TRANSFERIR_ALMACEN":
            return None
        name = data.get("part_name")
        quantity = data.get("quantity")
        if not isinstance(name, str) or not name.strip():
            return None
        if type(quantity) is not int or quantity <= 0:
            return None
        return {"name": name.strip(), "quantity": quantity}
    return None


_MISSING_ORIGIN = object()


def record_handoff(state: AgentState, origin: str = _MISSING_ORIGIN, *, origen: str = _MISSING_ORIGIN):
    """Audita herramientas y transferencias entre agentes."""
    if origin is _MISSING_ORIGIN:
        if origen is _MISSING_ORIGIN:
            raise TypeError("Missing origin")
        origin = origen
    elif origen is not _MISSING_ORIGIN:
        raise TypeError("Specify either origin or origen, not both")
    destination = detect_handoff(state["messages"])
    reason = handoff_reason(state["messages"]) if destination else None
    # Almacén entrega datos verificados a Ventas en la misma ejecución.
    batch = []
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break
        batch.append(message)
    current_inventory = any(
        message.name in {"consultar_inventario", "check_inventory"} and message.status != "error"
        and any(item.get("tool_call_id") == message.tool_call_id
                for item in state.get("inventory_results", []))
        for message in batch
    )
    if (origin == "almacen" and destination is None and current_inventory
            and not any(message.status == "error" or message.name in HANDOFF_TOOLS for message in batch)
            and state.get("required_parts") and not state.get("inventory_pending", True)):
        destination = evaluate_supply(state)["destination"]
        reason = "Entregar inventario verificado"
    history = list(state.get("handoff_history", []))
    count = state.get("handoff_count", 0)
    errors = list(state.get("errors", []))
    iterations = dict(state.get("tool_iterations", {}))
    iterations[origin] = iterations.get(origin, 0) + 1

    if iterations[origin] >= MAX_TOOL_ITERATIONS:
        errors.append(f"Límite de herramientas alcanzado por {origin}")
        return {
            "next_agent": "finalizar",
            "tool_iterations": iterations,
            "errors": errors,
            "messages": [AIMessage(content=(
                "No fue posible completar la solicitud "
                "dentro del límite de operaciones permitido."
            ))],
        }

    if destination is None:
        return {"next_agent": origin, "tool_iterations": iterations}

    def _reject_handoff(error):
        return {"next_agent": "finalizar", "tool_iterations": iterations,
                "errors": errors + [str(error)],
                "messages": [AIMessage(content="No se pudo completar la transferencia.")]}

    try:
        for entry in history:
            normalize_handoff_history_entry(entry)
        validate_handoff(origin, destination, reason, AGENT_NODES, state.get("request_revision"))
    except (ValueError, TypeError) as error:
        return _reject_handoff(error)

    selected = selected_handoff(state["messages"])
    data = None
    if selected is not None:
        try:
            data = json.loads(selected.content)
        except (ValueError, TypeError):
            pass
        if isinstance(data, dict):
            try:
                data = normalize_handoff_payload(data)
            except (ValueError, TypeError) as error:
                return _reject_handoff(error)
    inventory_query = None
    if selected is not None and selected.name in {"solicitar_inventario", "request_inventory"}:
        if isinstance(data, dict) and isinstance(data.get("query"), str):
            inventory_query = data["query"]

    if destination == origin:
        errors.append("Transferencia al mismo agente")
        return {
            "next_agent": "finalizar",
            "tool_iterations": iterations,
            "errors": errors,
            "messages": [AIMessage(content="No se pudo completar la transferencia.")],
        }

    if count >= MAX_HANDOFFS:
        errors.append("Límite de transferencias alcanzado")
        return {
            "next_agent": "finalizar",
            "tool_iterations": iterations,
            "errors": errors,
            "messages": [AIMessage(content=(
                "No fue posible completar la solicitud "
                "tras varios intentos de transferencia."
            ))],
        }

    pending_part = None
    supply_evaluation = evaluate_supply(state)
    if origin == "almacen" and destination in {"compras", "ventas"} and supply_evaluation["destination"] != destination:
        return _reject_handoff(ValueError("Destino incompatible con la disponibilidad de inventario verificada"))
    if origin == "compras" and destination == "ventas" and supply_evaluation["destination"] != "compras":
        return _reject_handoff(ValueError("Faltante de inventario sin vigencia confirmada"))
    if origin == "software" and destination == "ventas":
        scope = data.get("scope") if isinstance(data, dict) else None
        if scope != "solo_servicio" or not is_software_commercially_eligible(state):
            return _reject_handoff(ValueError("Software solo puede transferir a Ventas un servicio sin repuestos"))
    if origin == "tecnico" and destination == "ventas":
        scope = data.get("scope") if isinstance(data, dict) else None
        if scope == "repuestos":
            name = data.get("part_name")
            quantity = data.get("quantity")
            if is_part_reference_confirmed(state, name) and type(quantity) is int and quantity > 0:
                pending_part = {"name": name.strip(), "quantity": quantity}
                destination = "almacen"
            else:
                return {"next_agent": "finalizar", "tool_iterations": iterations,
                        "messages": [AIMessage(content=(
                            "Para verificar disponibilidad y cotizar el reemplazo, "
                            "¿qué tipo o modelo exacto de repuesto indicó el técnico? "
                            "Si no lo sabes, necesitamos una revisión para identificarlo."
                        ))]}
        elif scope != "solo_servicio":
            return {"next_agent": "finalizar", "tool_iterations": iterations,
                    "messages": [AIMessage(content=(
                        "Antes de cotizar, necesito aclarar si solicitas únicamente "
                        "una revisión de diagnóstico o una reparación con repuestos pendientes de verificar."
                    ))]}

    if origin == "tecnico" and destination == "almacen" and pending_part is None:
        pending_part = extract_part_handoff(state["messages"])
        if pending_part is None:
            errors.append("Transferencia a Almacén sin repuesto válido")
            return {
                "next_agent": "finalizar",
                "tool_iterations": iterations,
                "errors": errors,
                "messages": [AIMessage(content=(
                    "No fue posible identificar un repuesto válido para consultar."
                ))],
            }

    if pending_part is not None and not is_part_reference_confirmed(state, pending_part["name"]):
        return {"next_agent": "finalizar", "tool_iterations": iterations,
                "messages": [AIMessage(content=(
                    "¿Qué tipo o modelo exacto de repuesto indicó el técnico? "
                    "No puedo elegir una variante ni confirmar compatibilidad solo con un nombre genérico."
                ))]}

    # Impedir cotizaciones mientras falte verificar inventario.
    if (
        origin == "almacen"
        and destination == "ventas"
        and (state.get("inventory_pending", False)
             or (state.get("required_parts") and not all(
                 any(item.get("requested_name") == part["name"] and item.get("quantity") == part["quantity"]
                     for item in current_inventory_results(state)) for part in state["required_parts"])))
    ):
        errors.append("Inventario pendiente de verificar")
        return {
            "next_agent": "finalizar",
            "tool_iterations": iterations,
            "errors": errors,
            "messages": [AIMessage(content=(
                "No es posible continuar con la cotización "
                "porque falta verificar el inventario."
            ))],
        }

    try:
        record = make_handoff_record(state, origin, destination, reason, AGENT_NODES)
    except (ValueError, TypeError, KeyError) as error:
        return _reject_handoff(error)
    history.append({"origin": origin, "destination": destination})
    update = {
        "next_agent": destination,
        "handoff_count": count + 1,
        "handoff_history": history,
        "tool_iterations": iterations,
        "handoff_records": [*state.get("handoff_records", []), record],
    }
    if inventory_query is not None:
        update["inventory_query"] = inventory_query
    if destination == "almacen":
        required = list(state.get("required_parts", []))
        if pending_part:
            # Conservar otros componentes; una cantidad nueva sustituye la
            # solicitud anterior de esa referencia, sin acumular ambas.
            required = [part for part in required if part.get("name") != pending_part["name"]]
            required.append(pending_part)
        update.update(prepare_inventory_request(state, required))
        if inventory_query is not None:
            update["inventory_pending"] = True
    if origin == "almacen" and destination == "ventas":
        update["inventory_requested_by"] = None
    if origin in {"almacen", "compras"} and destination in {"compras", "ventas"}:
        update.update(inventory_checks=supply_evaluation["inventory_checks"],
                             out_of_stock_items=supply_evaluation["out_of_stock_items"])
    if destination == "compras":
        update["supplier_offers"] = []
    if origin == "compras" and destination == "ventas":
        update.update(inventory_requested_by=None, quote_scope="repuestos")
    if pending_part is not None:
        update["quote_scope"] = "repuestos"
    elif origin in {"tecnico", "software"} and destination == "ventas":
        update["quote_scope"] = "solo_servicio"
    elif origin == "almacen" and destination == "ventas":
        update["quote_scope"] = "repuestos"
    return update


def record_inventory_results(state: AgentState):
    """Registra inventario y verifica los repuestos requeridos."""
    results = current_inventory_results(state)
    errors = list(state.get("errors", []))
    requirements = state.get("required_parts", [])

    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break

        if message.name not in {"consultar_inventario", "check_inventory"}:
            continue

        if message.status == "error":
            errors.append("Error al consultar inventario")
            continue

        try:
            result = normalize_inventory_result(json.loads(message.content))

            if not isinstance(result, dict):
                raise ValueError("Resultado invalido")

            fields = {
                "requested_name", "name", "quantity",
                "stock", "unit_price", "available",
            }

            if not fields.issubset(result):
                raise ValueError("Faltan campos")

            name = result["requested_name"]
            quantity = result["quantity"]
            stock = result["stock"]
            price = result["unit_price"]
            available = result["available"]

            from decimal import Decimal, InvalidOperation

            if not isinstance(name, str) or not name.strip():
                raise ValueError("Nombre invalido")

            if type(quantity) is not int or quantity <= 0:
                raise ValueError("Cantidad invalida")

            if type(stock) is not int or stock < 0:
                raise ValueError("Stock invalido")

            if type(available) is not bool:
                raise ValueError("Disponibilidad invalida")

            try:
                decimal_price = Decimal(str(price))
            except (InvalidOperation, TypeError, ValueError):
                raise ValueError("Precio invalido")

            if not decimal_price.is_finite() or decimal_price < 0:
                raise ValueError("Precio invalido")

            if available != (stock >= quantity):
                raise ValueError("Disponibilidad inconsistente")

            if requirements and not any(part.get("name") == name and part.get("quantity") == quantity
                                      for part in requirements):
                raise ValueError("Resultado ajeno al requerimiento")

            result["tool_call_id"] = message.tool_call_id

            results = [
                item for item in results
                if item.get("tool_call_id") != message.tool_call_id
                and (item.get("requested_name"), item.get("quantity")) != (name, quantity)
            ]
            results.append(result)

        except (ValueError, TypeError):
            errors.append("Resultado de inventario inválido")

    def _matches_requirement(part, result):
        return (
            isinstance(result, dict)
            and result.get("requested_name") == part.get("name")
            and result.get("quantity") == part.get("quantity")
        )

    complete = bool(requirements) and all(
        any(_matches_requirement(part, result) for result in results)
        for part in requirements
    )

    return {
        "inventory_results": results,
        "inventory_revision": state.get("request_revision", 0) if results else None,
        "inventory_pending": not complete if requirements else
            state.get("inventory_pending", False),
        "errors": errors,
    }


def audit_support(state: AgentState):
    return record_handoff(state, "soporte")


def audit_hardware(state: AgentState):
    return record_handoff(state, "tecnico")


def audit_sales(state: AgentState):
    return record_handoff(state, "ventas")


def audit_warehouse(state: AgentState):
    return record_handoff(state, "almacen")


def audit_software(state: AgentState):
    return record_handoff(state, "software")


def audit_purchasing(state: AgentState):
    return record_handoff(state, "compras")


def audit_billing(state: AgentState):
    return record_handoff(state, "facturacion")


def audit_logistics(state: AgentState):
    return record_handoff(state, "logistica")


def route_next_agent(state: AgentState):
    return state.get("next_agent") or "finalizar"


def route_entry(state: AgentState):
    """Retoma al agente activo; las conversaciones nuevas empiezan en Soporte."""
    agent = state.get("current_agent", "soporte")
    return agent if agent in AGENT_NODES else "soporte"


def prepare_turn(state: AgentState):
    """Reinicia controles tras recuperar el historial, sin borrar datos de negocio."""
    messages = state.get("messages", [])
    start_index = next(
        (i for i in range(len(messages) - 1, -1, -1)
         if isinstance(messages[i], HumanMessage)),
        state.get("turn_start_index", 0),
    )
    return {
        "turn_start_index": start_index,
        "ticket_preparation_ready": False,
        "handoff_count": 0,
        "handoff_history": [],
        "handoff_records": [],
        "tool_iterations": {},
        "errors": [],
        "next_agent": None,
    }


detectar_handoff = detect_handoff
extraer_repuesto_handoff = extract_part_handoff
guardar_inventario = record_inventory_results
preparar_turno = prepare_turn
auditar_soporte = audit_support
auditar_tecnico = audit_hardware
auditar_ventas = audit_sales
auditar_almacen = audit_warehouse
auditar_software = audit_software
auditar_compras = audit_purchasing
auditar_facturacion = audit_billing
auditar_logistica = audit_logistics


def registrar_handoff(state: AgentState, origen: str):
    return record_handoff(state, origin=origen)


def build_graph(checkpointer=None, *, financial_repository=None, ticket_writes=False, quote_writes=False):
    """Construye la misma red; el consumidor puede aportar su checkpointer.

    Sin checkpointer admite invoke(state) y el historial gestionado por Conversation.
    La API aporta MemorySaver y thread_id para conservar conversaciones.
    """
    if financial_repository is not None and checkpointer is None:
        raise ValueError("Preparación financiera requiere checkpointer explícito")
    if quote_writes and (financial_repository is None or checkpointer is None):
        raise ValueError("Aceptación de cotizaciones requiere repositorio y checkpointer")
    builder = StateGraph(AgentState, context_schema=FinancialContext)
    for name, node in AGENT_NODES.items():
        if name == "ventas" and quote_writes:
            def sales_entry(state: AgentState, config, runtime: Runtime[FinancialContext]):
                from app.agents.decentralized.quote_operations import build_proposal, QuoteConflict
                from app.database.decentralized_repository import RetryConflict
                result = sales_node(state)
                if result.get("quote", {}).get("status") != "proposed":
                    return {**result, "proposal": None, "proposal_decision": None}
                if state.get("quote_receipt") is not None:
                    return result
                try:
                    proposal = build_proposal({**state, **result}, result["quote"],
                        authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
                        conversation_id=config.get("metadata", {}).get("conversation_id", config["configurable"]["thread_id"]),
                        repository=financial_repository)
                except (RetryConflict, ValueError, LookupError, KeyError, TypeError):
                    return {**result, "proposal": None, "proposal_decision": None,
                            "messages": [AIMessage(content="La propuesta todavía no permite aceptación: verifica el ticket, la revisión y el inventario vigente. No se guardó una cotización.")]}
                same = (state.get("proposal") or {}).get("proposal_id") == proposal["proposal_id"]
                patch = {**result, "proposal": proposal,
                         "proposal_decision": state.get("proposal_decision") if same else None}
                if not state.get("required_parts"):
                    patch.update(inventory_revision=proposal["request_revision"], inventory_pending=False)
                return patch
            node = sales_entry
        if name == "soporte" and financial_repository is not None:
            def support_entry(state: AgentState, runtime: Runtime[FinancialContext]):
                customer = (runtime.context or {}).get("authenticated_customer_id")
                return support_node(state, authenticated_customer_id=customer) if customer is not None else support_node(state)
            node = support_entry
        if name == "garantia" and financial_repository is not None:
            def warranty_entry(state: AgentState, runtime: Runtime[FinancialContext]):
                return warranty_node(state, repository=financial_repository,
                    authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"))
            node = warranty_entry
        if name == "logistica" and financial_repository is not None:
            def logistics_entry(state: AgentState, runtime: Runtime[FinancialContext]):
                return logistics_node(state, repository=financial_repository,
                    authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"))
            node = logistics_entry
        if name == "facturacion" and financial_repository is not None:
            # Trusted invocation context is not checkpointed or model-generated.
            def financial_entry(state: AgentState, runtime: Runtime[FinancialContext]):
                return billing_node(state, repository=financial_repository,
                    authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"))
            node = financial_entry
        builder.add_node(name, node)

    if quote_writes:
        def prepare_quote(state: AgentState, runtime: Runtime[FinancialContext]):
            from app.agents.decentralized.quote_operations import prepare_quote_decision
            context = runtime.context or {}
            patch = prepare_quote_decision(state,
                authenticated_customer_id=context.get("authenticated_customer_id"),
                conversation_id=context.get("quote_conversation_id"),
                proposal_id=context.get("quote_proposal_id"), action=context.get("quote_action"),
                repository=financial_repository)
            patch["messages"] = [AIMessage(content=("La cotización ya estaba aceptada y guardada; no se duplicó ni se registró un pago."
                if state.get("quote_receipt") is not None else
                "La propuesta fue rechazada; no se registró una cotización aceptada."
                if context.get("quote_action") == "reject_quote" else
                "La aceptación está preparada; todavía no se confirmó el guardado de la cotización."))]
            return patch

        def execute_quote(state: AgentState, config, runtime: Runtime[FinancialContext]):
            from app.agents.decentralized.quote_operations import validate_pending_quote, QuoteConflict
            from app.database.decentralized_repository import _id, _money
            from copy import deepcopy
            context = runtime.context or {}
            if context.get("quote_action") != "accept_quote":
                raise QuoteConflict("La ejecución requiere aceptación autenticada")
            operation = validate_pending_quote(state,
                authenticated_customer_id=context.get("authenticated_customer_id"),
                conversation_id=context.get("quote_conversation_id"), proposal_id=context.get("quote_proposal_id"))
            saved = checkpointer.get_tuple({"configurable": {
                "thread_id": config["configurable"]["thread_id"], "checkpoint_ns": ""}})
            if saved is None or saved.checkpoint.get("channel_values", {}).get("pending_quote_operation") != operation:
                raise QuoteConflict("La operación no está confirmada en checkpoint")
            row = financial_repository.create_accepted_quote(**operation["payload"])
            proposal = state["proposal"]
            if (row.get("ticket_id") != operation["payload"]["ticket_id"] or row.get("status") != "ACCEPTED"
                    or row.get("quote_type") != proposal["quote_type"]
                    or _money(row.get("total_amount")) != proposal["total_amount"]
                    or _money(row.get("labor_cost")) != proposal["labor_cost"]):
                raise QuoteConflict("Respuesta persistida incompatible; requiere reconciliación")
            quote_id = _id(row.get("id"))
            return {"quote_id": quote_id, "quote_status": "ACCEPTED", "ticket_status": "QUOTED",
                    "pending_quote_operation": None,
                    "quote_receipt": dict(proposal_id=operation["proposal_id"], quote_id=quote_id,
                                          payload=deepcopy(operation["payload"])),
                    "quote": {**state["quote"], "status": "confirmed"},
                    "messages": [AIMessage(content="La cotización quedó aceptada y guardada con el identificador " + str(quote_id) + ". No se ha registrado ni confirmado un pago.")]}

        builder.add_node("preparar_cotizacion", prepare_quote)
        builder.add_node("ejecutar_cotizacion", execute_quote)
        builder.add_conditional_edges("preparar_cotizacion",
            lambda state: "execute" if state.get("pending_quote_operation") else "done",
            {"execute": "ejecutar_cotizacion", "done": END})
        builder.add_edge("ejecutar_cotizacion", END)

    if ticket_writes and (financial_repository is None or checkpointer is None):
        raise ValueError("Creación de tickets requiere repositorio y checkpointer")

    def prepare_ticket(state: AgentState, runtime: Runtime[FinancialContext]):
        from app.agents.decentralized.ticket_operations import validate_pending_ticket_operation
        if state.get("ticket_correction_required"):
            raise ValueError("La operación requiere reconciliación")
        operation = validate_pending_ticket_operation(state.get("pending_ticket_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        return {"pending_ticket_operation": operation, "ticket_preparation_ready": False,
                "messages": [AIMessage(content="La solicitud está preparada y todavía no se creó un ticket. Responde continuar para registrar esta misma solicitud y derivarla al especialista.")]}

    def execute_ticket(state: AgentState, config, runtime: Runtime[FinancialContext]):
        from app.agents.decentralized.ticket_operations import validate_pending_ticket_operation
        from app.database.decentralized_repository import _id
        operation = validate_pending_ticket_operation(state.get("pending_ticket_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        if state.get("ticket_correction_required") or state.get("ticket_id") is not None:
            raise ValueError("Operación de ticket incompatible")
        # Check the completed preparation checkpoint, not the current task's
        # private namespace. API invokes with durability='sync'. Fail closed.
        saved = checkpointer.get_tuple({"configurable": {
            "thread_id": config["configurable"]["thread_id"], "checkpoint_ns": ""}})
        if saved is None or saved.checkpoint.get("channel_values", {}).get("pending_ticket_operation") != operation:
            raise RuntimeError("Operación pendiente no confirmada en checkpoint")
        row = financial_repository.create_ticket(**operation["payload"])
        if any(row.get(key) != value for key, value in operation["payload"].items()):
            raise RuntimeError("Respuesta de ticket incompatible")
        ticket_id = _id(row.get("id"))
        from app.agents.decentralized.policy import classify_support_triage
        kind = operation["payload"]["request_type"]
        destination = {"SALE": "ventas", "PC_BUILD": "ventas", "SUPPORT": "software",
                       "WARRANTY_CLAIM": "garantia", "REPAIR": "tecnico"}[kind]
        if kind == "REPAIR" and classify_support_triage({"messages": [HumanMessage(content=operation["payload"]["failure_description"])]}) == "software":
            destination = "software"
        transfer = handoff("soporte", {"ventas": "transfer_to_sales", "software": "transfer_to_software",
                           "garantia": "transfer_to_warranty", "tecnico": "transfer_to_hardware"}[destination],
                           reason="Continuar solicitud con ticket persistido y cliente autenticado")
        transfer["messages"].insert(0, AIMessage(content="Tu solicitud quedó registrada con el código " + row["code"] + "."))
        return {**transfer, "ticket_id": ticket_id, "ticket_code": row["code"],
                "ticket_status": row["status"], "request_type": kind,
                "pending_ticket_operation": None, "ticket_preparation_ready": False}

    if ticket_writes:
        builder.add_node("preparar_ticket", prepare_ticket)
        builder.add_node("ejecutar_ticket", execute_ticket)
        builder.add_edge("preparar_ticket", "ejecutar_ticket")
        builder.add_edge("ejecutar_ticket", "soporte_tools")

    def prepare_warranty(state: AgentState, runtime: Runtime[FinancialContext]):
        operation = validate_pending_warranty_operation(state.get("pending_warranty_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        return {"pending_warranty_operation": operation}

    def execute_warranty(state: AgentState, runtime: Runtime[FinancialContext]):
        operation = validate_pending_warranty_operation(state.get("pending_warranty_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        if state.get("ticket_id") != operation["payload"]["ticket_id"]:
            raise ValueError("Ticket pendiente incompatible")
        row = financial_repository.create_warranty_claim(**operation["payload"])
        ticket = financial_repository.get_ticket(customer_id=operation["payload"]["customer_id"], ticket_id=row["ticket_id"])
        patch = {"pending_warranty_operation": None, "warranty_preparation_ready": False,
                 "warranty_claim_id": row["id"], "claim_code": row["claim_code"],
                 "warranty_id": row["warranty_id"], "ticket_status": ticket["status"],
                 "warranty_claim": {"reason": row["reason"], "status": row["status"]}}
        try:
            financial_repository.get_logistics_context(customer_id=operation["payload"]["customer_id"], ticket_id=row["ticket_id"])
        except (ValueError, LookupError):
            return {**patch, "messages": [AIMessage(content="Reclamo persistido; sus condiciones actuales no permiten coordinar ingreso. No hay reparación aprobada.")]}
        return {**patch, **handoff("garantia", "transfer_to_logistics", reason="Coordinar ingreso de reclamo persistido IN_REVIEW")}

    builder.add_node("preparar_garantia", prepare_warranty)
    builder.add_node("ejecutar_garantia", execute_warranty)
    builder.add_edge("preparar_garantia", "ejecutar_garantia")
    builder.add_conditional_edges("ejecutar_garantia", tools_condition, {"tools": "garantia_tools", "__end__": END})

    def warranty_route(state):
        if tools_condition(state) == "tools":
            return "tools"
        return "prepare" if (financial_repository is not None and state.get("pending_warranty_operation")
                             and state.get("warranty_preparation_ready") is True) else "__end__"

    def prepare_payment(state: AgentState, runtime: Runtime[FinancialContext]):
        pending = validate_pending_payment_operation(state.get("pending_payment_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        # A separate superstep records exactly the prepared operation. No LLM.
        return {"pending_payment_operation": pending}

    def execute_payment(state: AgentState, runtime: Runtime[FinancialContext]):
        validate_pending_payment_operation(state.get("pending_payment_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        return {"messages": [AIMessage(content="La operación pendiente fue recuperada. La escritura financiera continúa deshabilitada; no se ha registrado ni confirmado un pago.")]}

    builder.add_node("preparar_pago", prepare_payment)
    builder.add_node("ejecutar_pago", execute_payment)
    builder.add_edge("preparar_pago", "ejecutar_pago")
    builder.add_edge("ejecutar_pago", END)

    def prepare_logistics(state: AgentState, runtime: Runtime[FinancialContext]):
        operation = validate_pending_logistics_operation(state.get("pending_logistics_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        return {"pending_logistics_operation": operation}

    def execute_logistics(state: AgentState, runtime: Runtime[FinancialContext]):
        operation = validate_pending_logistics_operation(state.get("pending_logistics_operation"),
            authenticated_customer_id=(runtime.context or {}).get("authenticated_customer_id"),
            request_revision=state.get("request_revision"))
        if state.get("ticket_id") != operation["payload"]["ticket_id"]:
            raise ValueError("Ticket pendiente incompatible")
        row = financial_repository.create_initial_logistics(**operation["payload"])
        return {"pending_logistics_operation": None, "logistics_record_id": row["id"],
                "logistics_preparation_ready": False,
                "logistics": {key:row.get(key) for key in ("mode", "status", "courier_company", "shipping_address",
                               "recipient_name", "recipient_phone", "tracking_number", "scheduled_date", "received_at", "delivered_at")},
                "messages": [AIMessage(content="El registro logístico está confirmado en el sistema. Su estado es " + row["status"] + ". Este registro no confirma recepción física, preparación, despacho ni entrega.")]}

    builder.add_node("preparar_logistica", prepare_logistics)
    builder.add_node("ejecutar_logistica", execute_logistics)
    builder.add_edge("preparar_logistica", "ejecutar_logistica")
    builder.add_edge("ejecutar_logistica", END)

    def logistics_route(state):
        if tools_condition(state) == "tools":
            return "tools"
        return "prepare" if (financial_repository is not None and state.get("pending_logistics_operation")
                             and state.get("logistics_preparation_ready") is True) else "__end__"

    def financial_route(state):
        if tools_condition(state) == "tools":
            return "tools"
        return "prepare" if financial_repository is not None and state.get("pending_payment_operation") else "__end__"

    for name, tools in (
        ("soporte", _resolve_support_tools()),
        ("tecnico", _resolve_hardware_tools()),
        ("ventas", _resolve_sales_tools()),
        ("almacen", _resolve_warehouse_tools()),
        ("software", software_tools),
        ("compras", _resolve_purchasing_tools()),
        ("facturacion", _resolve_billing_tools()),
        ("logistica", _resolve_logistics_tools()),
        ("garantia", _resolve_warranty_tools()),
    ):
        if name in {"soporte", "software", "tecnico", "compras", "facturacion", "logistica", "garantia", "almacen", "ventas"}:
            if name == "soporte":
                from app.agents.decentralized.tools.support_handoff_tools import legacy_handoff_tools
            elif name == "software":
                from app.agents.decentralized.tools.software_handoff_tools import legacy_handoff_tools
            elif name == "tecnico":
                from app.agents.decentralized.tools.hardware_handoff_tools import legacy_handoff_tools
            elif name == "compras":
                from app.agents.decentralized.tools.purchasing_handoff_tools import legacy_handoff_tools
            elif name == "facturacion":
                from app.agents.decentralized.tools.billing_handoff_tools import legacy_handoff_tools
            elif name == "logistica":
                from app.agents.decentralized.tools.logistics_handoff_tools import legacy_handoff_tools
            elif name == "garantia":
                from app.agents.decentralized.tools.warranty_handoff_tools import legacy_handoff_tools
            elif name == "almacen":
                from app.agents.decentralized.tools.warehouse_handoff_tools import legacy_handoff_tools
            else:
                from app.agents.decentralized.tools.sales_handoff_tools import legacy_handoff_tools
            registered = {item.name for item in tools}
            tools = [*tools, *(item for item in legacy_handoff_tools if item.name not in registered)]
        if name == "ventas":
            from app.agents.decentralized.tools.ventas_tools import generar_cotizacion
            if not any(item.name == "generar_cotizacion" for item in tools):
                tools = [*tools, generar_cotizacion]
            from app.agents.decentralized.tools.inventory_request_tools import legacy_inventory_request_tools
            registered = {item.name for item in tools}
            tools = [*tools, *(item for item in legacy_inventory_request_tools if item.name not in registered)]
        if name == "facturacion":
            tools = [*tools, consultar_capacidades_financieras]
        if name == "tecnico":
            tools = [*tools, diagnosticar_problema]
        if name == "compras":
            tools = [*tools, consultar_fuentes_abastecimiento]
        if name == "almacen" and not any(item.name == "consultar_inventario" for item in tools):
            tools = [*tools, consultar_inventario]
        if name == "soporte":
            from app.agents.decentralized.tools.soporte_tools import (
                authenticated_ticket_tool, authenticated_ticket_status_tool, consultar_estado_ticket,
            )
            if financial_repository is not None:
                tools = [item for item in tools if item.name not in {"get_ticket_status", "consultar_estado_ticket"}]
                tools = [*tools, authenticated_ticket_status_tool(financial_repository),
                         authenticated_ticket_tool(financial_repository)]
            elif not any(item.name == "consultar_estado_ticket" for item in tools):
                tools = [*tools, consultar_estado_ticket]
        builder.add_node(f"{name}_tools", ToolNode(tools, handle_tool_errors=True))

    builder.add_node("guardar_inventario", record_inventory_results)
    builder.add_node("auditar_soporte", audit_support)
    builder.add_node("auditar_tecnico", audit_hardware)
    builder.add_node("auditar_ventas", audit_sales)
    builder.add_node("auditar_almacen", audit_warehouse)
    builder.add_node("auditar_software", audit_software)
    builder.add_node("auditar_compras", audit_purchasing)
    builder.add_node("auditar_facturacion", audit_billing)
    builder.add_node("auditar_logistica", audit_logistics)
    builder.add_node("auditar_garantia", lambda state: record_handoff(state, "garantia"))

    builder.add_node("preparar_turno", prepare_turn)
    builder.add_edge(START, "preparar_turno")
    if quote_writes:
        def quote_entry(state: AgentState, runtime: Runtime[FinancialContext]):
            from app.agents.decentralized.quote_operations import QuoteConflict
            if (runtime.context or {}).get("quote_action") in {"accept_quote", "reject_quote"}:
                return "preparar_cotizacion"
            if state.get("pending_quote_operation") is not None:
                raise QuoteConflict("Hay una cotización pendiente de reintento; no se puede reemplazar")
            return route_entry(state)
        builder.add_conditional_edges("preparar_turno", quote_entry,
            {**{name: name for name in AGENT_NODES}, "preparar_cotizacion": "preparar_cotizacion"})
    else:
        builder.add_conditional_edges("preparar_turno", route_entry,
                                      {name: name for name in AGENT_NODES})
    for agent in AGENT_NODES:
        if agent == "soporte" and ticket_writes:
            def support_route(state):
                if tools_condition(state) == "tools":
                    return "tools"
                return "prepare" if state.get("ticket_preparation_ready") and not state.get("ticket_correction_required") else "__end__"
            builder.add_conditional_edges(agent, support_route,
                {"tools": "soporte_tools", "prepare": "preparar_ticket", "__end__": END})
            continue
        if agent == "garantia":
            builder.add_conditional_edges(agent, warranty_route,
                {"tools": "garantia_tools", "prepare": "preparar_garantia", "__end__": END})
            continue
        if agent == "logistica":
            builder.add_conditional_edges(agent, logistics_route,
                {"tools": "logistica_tools", "prepare": "preparar_logistica", "__end__": END})
            continue
        if agent == "facturacion":
            builder.add_conditional_edges(agent, financial_route,
                {"tools": "facturacion_tools", "prepare": "preparar_pago", "__end__": END})
            continue
        builder.add_conditional_edges(
            agent,
            tools_condition,
            {"tools": f"{agent}_tools", "__end__": END},
        )

    builder.add_edge("soporte_tools", "auditar_soporte")
    builder.add_edge("tecnico_tools", "auditar_tecnico")
    builder.add_edge("ventas_tools", "auditar_ventas")
    builder.add_edge("almacen_tools", "guardar_inventario")
    builder.add_edge("guardar_inventario", "auditar_almacen")
    builder.add_edge("software_tools", "auditar_software")
    builder.add_edge("compras_tools", "auditar_compras")
    builder.add_edge("facturacion_tools", "auditar_facturacion")
    builder.add_edge("logistica_tools", "auditar_logistica")
    builder.add_edge("garantia_tools", "auditar_garantia")

    routes = {**{name: name for name in AGENT_NODES}, "finalizar": END}
    for auditor in (
        "auditar_soporte", "auditar_tecnico",
        "auditar_almacen", "auditar_ventas",
        "auditar_software",
        "auditar_compras",
        "auditar_facturacion",
        "auditar_logistica",
        "auditar_garantia",
    ):
        builder.add_conditional_edges(auditor, route_next_agent, routes)

    # Static interrupt forces a saved checkpoint before the execution superstep.
    # Resume requires a trusted caller using invoke(None, context=...) explicitly.
    interrupts = ["ejecutar_pago", "ejecutar_logistica", "ejecutar_garantia"] if financial_repository is not None else []
    if ticket_writes:
        interrupts.append("ejecutar_ticket")
    if quote_writes:
        interrupts.append("ejecutar_cotizacion")
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupts or None)


# Compatible con scripts y Conversation que invocan sin thread_id.
graph = build_graph()
