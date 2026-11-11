"""Aceptación explícita y recuperable; sin SQL ni decisiones delegadas al modelo."""
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json

from app.database.decentralized_repository import _id, _money, _quantity, _subtotal, _total, RetryConflict
from app.agents.decentralized.policy import current_inventory_results


class QuoteConflict(RetryConflict):
    pass


def _revision(value):
    if type(value) is not int or value < 0:
        raise QuoteConflict("Revisión de propuesta inválida")
    return value


def _amount(value):
    if not isinstance(value, (str, Decimal)):
        raise QuoteConflict("Importe conversacional inválido")
    return _money(Decimal(value))


def _customer(state, customer):
    customer = _id(customer)
    if _id(state.get("customer_id")) != customer:
        raise QuoteConflict("Identidad incompatible con la propuesta")
    return customer


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str, ensure_ascii=False).encode()).hexdigest()


def _content(proposal):
    return {key: value for key, value in proposal.items() if key != "proposal_id"}


def build_proposal(state, quote, *, authenticated_customer_id, conversation_id, repository):
    """Solo ofrece una versión completa respaldada por ticket e inventario propios."""
    customer = _customer(state, authenticated_customer_id)
    revision = _revision(state.get("request_revision"))
    if not isinstance(conversation_id, str) or not conversation_id:
        raise QuoteConflict("Conversación inválida")
    ticket = repository.get_ticket(customer_id=customer, ticket_id=_id(state.get("ticket_id")))
    kind = ticket["request_type"]
    if (ticket["customer_id"] != customer or ticket["id"] != state["ticket_id"]
            or kind != state.get("request_type") or ticket["status"] not in {"NEW", "IN_DIAGNOSIS"}):
        raise QuoteConflict("Ticket incompatible con la propuesta")
    # PC_BUILD remains blocked until component/compatibility validation is complete.
    if kind not in {"SALE", "REPAIR", "SUPPORT"} or quote.get("status") != "proposed":
        raise QuoteConflict("La propuesta no está completa")
    labor = Decimal("0.00") if kind == "SALE" else Decimal("35.00")
    lines, snapshots = [], []
    required = state.get("required_parts", [])
    results = current_inventory_results(state)
    if required:
        if state.get("inventory_pending") or len(results) != len(required):
            raise QuoteConflict("Inventario pendiente u obsoleto")
        seen = set()
        for result in results:
            part_id = _id(result.get("inventory_id"))
            quantity = _quantity(result.get("quantity"))
            if result.get("found") is not True or result.get("available") is not True or part_id in seen:
                raise QuoteConflict("Referencia no seleccionada o duplicada")
            seen.add(part_id)
            price = _amount(result["unit_price"])
            part = repository.get_inventory(spare_part_id=part_id, quantity=quantity)
            if (not part or part["id"] != part_id or not part.get("available")
                    or part["current_stock"] != result["stock"] or _money(part["unit_price"]) != price):
                raise QuoteConflict("Inventario cambió; consulta una propuesta nueva")
            lines.append(dict(spare_part_id=part_id, custom_item_name=None, quantity=quantity,
                              unit_price=price, subtotal=_subtotal(price, quantity)))
            snapshots.append(dict(id=part_id, stock=part["current_stock"], name=part["name"]))
    elif kind == "SALE" or state.get("quote_scope") != "solo_servicio":
        raise QuoteConflict("Faltan artículos o un servicio definido")
    lines.sort(key=lambda line: line["spare_part_id"])
    snapshots.sort(key=lambda item: item["id"])
    parts = _total(line["subtotal"] for line in lines)
    total = _total([labor, parts])
    if (_amount(quote.get("total")) != total or _amount(quote.get("labor_total")) != labor
            or _amount(quote.get("known_parts_subtotal")) != parts or total <= 0):
        raise QuoteConflict("Importes de propuesta incompatibles")
    content = dict(customer_id=customer, ticket_id=ticket["id"], conversation_id=conversation_id,
                   request_revision=revision, quote_type="DIRECT_SALE" if kind == "SALE" else "REPAIR",
                   request_type=kind,
                   currency="PEN", labor_cost=labor, parts_cost=parts, total_amount=total,
                   lines=lines, inventory_snapshot=snapshots)
    return {**content, "proposal_id": _digest(content)}


def validate_proposal(state, *, authenticated_customer_id, conversation_id, proposal_id):
    try:
        customer = _customer(state, authenticated_customer_id)
    except (ValueError, TypeError):
        raise QuoteConflict("No hay una propuesta propia vigente") from None
    proposal = state.get("proposal")
    if (not isinstance(proposal, dict) or not isinstance(proposal_id, str) or not proposal_id
            or proposal.get("proposal_id") != proposal_id or _digest(_content(proposal)) != proposal_id
            or proposal.get("customer_id") != customer or proposal.get("conversation_id") != conversation_id
            or proposal.get("ticket_id") != state.get("ticket_id")
            or _revision(proposal.get("request_revision")) != _revision(state.get("request_revision"))):
        raise QuoteConflict("La propuesta no existe o fue reemplazada; consulta la versión vigente")
    return deepcopy(proposal)


def quote_response(state):
    """Adaptador de presentación; la API autoriza la conversación antes de usarlo."""
    proposal = state.get("proposal")
    if not isinstance(proposal, dict) or not proposal.get("proposal_id"):
        return None
    if _digest(_content(proposal)) != proposal["proposal_id"]:
        return None
    decision = state.get("proposal_decision") or {}
    receipt = state.get("quote_receipt") or {}
    status = "proposed"
    if receipt.get("proposal_id") == proposal["proposal_id"]:
        status = "confirmed"
    elif decision.get("proposal_id") == proposal["proposal_id"] and decision.get("accepted") is False:
        status = "rejected"
    names = {item["id"]: item["name"] for item in proposal["inventory_snapshot"]}
    return dict(proposal_id=proposal["proposal_id"], status=status, currency=proposal["currency"],
                total=f"{proposal['total_amount']:.2f}",
                lines=[dict(label="Mano de obra", amount=f"{proposal['labor_cost']:.2f}"),
                       *(dict(label=f"{names[line['spare_part_id']]} × {line['quantity']}", amount=f"{line['subtotal']:.2f}")
                         for line in proposal["lines"])])


def quote_requires_retry(graph, config, snapshot):
    state = snapshot.values
    if state.get("pending_quote_operation") is not None or "ejecutar_cotizacion" in snapshot.next:
        return True
    if state.get("quote_receipt") is not None:
        saved = graph.checkpointer.get_tuple({"configurable": {
            "thread_id": config["configurable"]["thread_id"], "checkpoint_ns": ""}})
        return (saved is None or saved.checkpoint.get("channel_values", {}).get("pending_quote_operation") is not None
                or saved.checkpoint.get("channel_values", {}).get("quote_receipt") != state["quote_receipt"])
    return False


def quote_payload(proposal):
    return dict(customer_id=proposal["customer_id"], ticket_id=proposal["ticket_id"],
                quote_type=proposal["quote_type"], labor_cost=proposal["labor_cost"],
                lines=deepcopy(proposal["lines"]), explicitly_accepted=True,
                observations="SUPPORT" if proposal.get("request_type") == "SUPPORT" else None)


def validate_pending_quote(state, *, authenticated_customer_id, conversation_id, proposal_id):
    from app.agents.decentralized.state import proposal_is_accepted
    proposal = validate_proposal(state, authenticated_customer_id=authenticated_customer_id,
                                 conversation_id=conversation_id, proposal_id=proposal_id)
    expected = dict(proposal_id=proposal_id, conversation_id=conversation_id,
                    request_revision=proposal["request_revision"], payload=quote_payload(proposal))
    if state.get("pending_quote_operation") != expected or not proposal_is_accepted(state):
        raise QuoteConflict("La operación pendiente es incompatible; requiere reconciliación")
    return deepcopy(expected)


def prepare_quote_decision(state, *, authenticated_customer_id, conversation_id, proposal_id,
                           action, repository):
    proposal = validate_proposal(state, authenticated_customer_id=authenticated_customer_id,
                                 conversation_id=conversation_id, proposal_id=proposal_id)
    if action not in {"accept_quote", "reject_quote"}:
        raise QuoteConflict("Acción de propuesta inválida")
    if state.get("pending_quote_operation") is not None:
        raise QuoteConflict("La operación requiere reintento")
    ticket = repository.get_ticket(customer_id=proposal["customer_id"], ticket_id=proposal["ticket_id"])
    receipt = state.get("quote_receipt")
    if receipt is not None:
        row = repository.get_quote(customer_id=proposal["customer_id"], quote_id=_id(receipt.get("quote_id")))
        if (action != "accept_quote" or receipt.get("proposal_id") != proposal_id
                or receipt.get("payload") != quote_payload(proposal) or receipt["quote_id"] != state.get("quote_id")
                or ticket["id"] != proposal["ticket_id"] or ticket["customer_id"] != proposal["customer_id"]
                or row["id"] != receipt["quote_id"] or row["ticket_id"] != proposal["ticket_id"]
                or row["status"] != "ACCEPTED" or _money(row["total_amount"]) != proposal["total_amount"]):
            raise QuoteConflict("La cotización confirmada requiere reconciliación")
        return {}
    if (ticket["customer_id"] != proposal["customer_id"] or ticket["id"] != proposal["ticket_id"]
            or ticket["request_type"] != proposal["request_type"]
            or ticket["status"] not in {"NEW", "IN_DIAGNOSIS"}):
        raise QuoteConflict("Ticket incompatible con la decisión")
    decision = dict(proposal_id=proposal_id, request_revision=proposal["request_revision"],
                    accepted=action == "accept_quote", explicit=True)
    if action == "reject_quote":
        return {"proposal_decision": decision, "quote": {**state["quote"], "status": "rejected"}}
    if (state.get("proposal_decision") or {}).get("accepted") is False:
        raise QuoteConflict("La propuesta fue rechazada; solicita otra propuesta")
    from app.agents.decentralized.state import proposal_is_accepted
    if not proposal_is_accepted({**state, "proposal_decision": decision}):
        raise QuoteConflict("La propuesta o su inventario ya no están vigentes")
    for line, snapshot in zip(proposal["lines"], proposal["inventory_snapshot"]):
        part = repository.get_inventory(spare_part_id=line["spare_part_id"], quantity=line["quantity"])
        if (not part or part["id"] != line["spare_part_id"] or not part.get("available")
                or part["current_stock"] != snapshot["stock"] or _money(part["unit_price"]) != line["unit_price"]):
            raise QuoteConflict("Precio o stock cambió; consulta y acepta una propuesta nueva")
    operation = dict(proposal_id=proposal_id, conversation_id=conversation_id,
                     request_revision=proposal["request_revision"], payload=quote_payload(proposal))
    return {"proposal_decision": decision, "pending_quote_operation": operation}


def apply_quote_action(graph, config, *, authenticated_customer_id, conversation_id, proposal_id, action):
    """El consumidor autentica y mantiene el advisory lock durante ambas invocaciones."""
    snapshot = graph.get_state(config)
    state = snapshot.values
    proposal = validate_proposal(state, authenticated_customer_id=authenticated_customer_id,
                                 conversation_id=conversation_id, proposal_id=proposal_id)
    context = dict(authenticated_customer_id=authenticated_customer_id,
                   quote_conversation_id=conversation_id, quote_proposal_id=proposal_id, quote_action=action)
    receipt = state.get("quote_receipt")
    if receipt is not None:
        if (action != "accept_quote" or receipt.get("proposal_id") != proposal_id
                or receipt.get("payload") != quote_payload(proposal) or receipt.get("quote_id") != state.get("quote_id")):
            raise QuoteConflict("Cotización confirmada incompatible con la acción")
        if snapshot.next:
            raise QuoteConflict("Otra operación está pendiente de reanudación")
        # get_state() can include completed task writes not yet materialized in
        # the latest full checkpoint. Resume that superstep before new input.
        checkpoint_config = {"configurable": {
            "thread_id": config["configurable"]["thread_id"], "checkpoint_ns": ""}}
        saved = graph.checkpointer.get_tuple(checkpoint_config)
        if saved is None:
            raise QuoteConflict("No se pudo recuperar la confirmación en checkpoint")
        values = saved.checkpoint.get("channel_values", {})
        if values.get("quote_receipt") != receipt or values.get("pending_quote_operation") is not None:
            graph.invoke(None, config=config, context=context, durability="sync")
            saved = graph.checkpointer.get_tuple(checkpoint_config)
            if (saved is None or saved.checkpoint.get("channel_values", {}).get("quote_receipt") != receipt
                    or saved.checkpoint.get("channel_values", {}).get("pending_quote_operation") is not None):
                raise QuoteConflict("La confirmación requiere reconciliación de checkpoint")
        return graph.invoke({}, config=config, context=context, durability="sync")
    if state.get("pending_quote_operation") is not None:
        if action != "accept_quote":
            raise QuoteConflict("Hay una escritura incierta; reintenta antes de rechazar")
        validate_pending_quote(state, authenticated_customer_id=authenticated_customer_id,
                               conversation_id=conversation_id, proposal_id=proposal_id)
        if tuple(snapshot.next) != ("ejecutar_cotizacion",):
            raise QuoteConflict("La operación pendiente requiere reconciliación")
    else:
        if snapshot.next:
            raise QuoteConflict("Otra operación está pendiente de reanudación")
        result = graph.invoke({}, config=config, context=context, durability="sync")
        if action == "reject_quote":
            return result
        snapshot = graph.get_state(config)
        if tuple(snapshot.next) != ("ejecutar_cotizacion",):
            raise QuoteConflict("La aceptación no quedó preparada")
    return graph.invoke(None, config=config, context=context, durability="sync")
