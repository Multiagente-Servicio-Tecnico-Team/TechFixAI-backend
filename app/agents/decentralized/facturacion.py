"""Isolated deterministic financial agent. No write path or LLM initialization.

repository and authenticated_customer_id must be injected by a trusted consumer.
Preparing a pending operation is not a durable checkpoint or a confirmed payment.
"""
from langchain_core.messages import AIMessage
from app.agents.decentralized.state import AgentState
from app.agents.decentralized.payment_operations import (
    prepare_pending_payment_operation, generate_payment_code,
)
from app.database.decentralized_repository import _id, _money, RetryConflict
from app.agents.decentralized.policy import handoff
from app.agents.decentralized.tools.facturacion_tools import (
    transferir_a_soporte, transferir_a_ventas, get_financial_capabilities,
)

from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica

facturacion_tools = [transferir_a_soporte, transferir_a_ventas, get_financial_capabilities, transferir_a_logistica]

SYSTEM_PROMPT = """Eres Facturación y Pagos de la red descentralizada.
Ventas conserva los precios y la cotización. Solo una cotización SQL ACCEPTED,
del cliente y ticket correctos, permite preparar una orden PENDING.
Una orden pendiente no acredita pago recibido. No confirmes COMPLETED por chat.
No emitas factura fiscal ni apruebes reembolsos sin herramientas autorizadas.
No anuncies códigos de pagos antes del commit. Logística revalida precondiciones SQL.
La creación de pagos está deshabilitada hasta validar recuperación durable previa.
"""


def facturacion_node(state: AgentState, *, repository=None, authenticated_customer_id=None):
    def response(text):
        return {"current_agent": "facturacion", "messages": [AIMessage(content=text)]}
    # Capabilities, not keyword-derived commercial actions. User assertions and
    # conversational quote/payment status never authorize financial changes.
    if state.get("intent") == "REFUND":
        return response("La solicitud de reembolso requiere localizar y verificar el pago y el saldo reembolsable. Esa operación no está habilitada; no se ha registrado ni aprobado un reembolso.")
    if state.get("payment_id") is not None or state.get("payment_code") is not None:
        if repository is not None and authenticated_customer_id is not None and state.get("payment_id") is not None:
            try:
                customer = _id(authenticated_customer_id)
                if _id(state.get("customer_id")) != customer:
                    raise ValueError("Identidad incompatible")
                payment = repository.get_payment(customer_id=customer, payment_id=_id(state["payment_id"]))
                if (payment["ticket_id"] != state.get("ticket_id") or payment["quote_id"] != state.get("quote_id")
                        or payment["status"] not in {"PENDING", "COMPLETED"}):
                    raise ValueError("Pago incompatible")
                repository.get_logistics_context(customer_id=customer,ticket_id=_id(state["ticket_id"]))
                # Read-only verified transition; never creates or confirms a payment.
                return handoff("facturacion", "transferir_a_logistica",
                               motivo="Coordinar logística con pago persistido verificado; pendiente no significa cobro recibido")
            except Exception:
                return response("No fue posible verificar el pago y las precondiciones logísticas. No se ha creado otra orden ni confirmado un cobro.")
        return response("Para informar el estado del pago necesitamos una consulta autorizada al registro financiero. Un mensaje o una captura no confirma el cobro. No se ha creado otra orden ni emitido una factura fiscal.")
    if repository is None or authenticated_customer_id is None:
        return response("Necesito una identidad autenticada y una consulta autorizada de la cotización persistida. No se ha creado una orden de pago.")
    try:
        customer_id = _id(authenticated_customer_id)
        if _id(state.get("customer_id")) != customer_id:
            raise RetryConflict("Identidad incompatible")
        ticket_id, quote_id = _id(state.get("ticket_id")), _id(state.get("quote_id"))
        ticket = repository.get_ticket(customer_id=customer_id, ticket_id=ticket_id)
        quote = repository.get_quote(customer_id=customer_id, quote_id=quote_id)
        if (ticket["id"] != ticket_id or ticket["customer_id"] != customer_id
                or quote["id"] != quote_id or quote["ticket_id"] != ticket_id):
            raise RetryConflict("Relaciones incompatibles")
        if quote["status"] != "ACCEPTED":
            return response("Ventas debe confirmar y guardar la cotización aceptada antes de preparar una orden de pago.")
        amount = _money(quote["total_amount"])
        if amount <= 0:
            return response("El importe persistido no permite registrar una orden de pago; se requiere revisión comercial.")
        if ticket["status"] != "QUOTED":
            return response("El ticket requiere reconciliación de su estado antes de preparar otra orden de pago.")
        code = None if state.get("pending_payment_operation") is not None else generate_payment_code()
        patch = prepare_pending_payment_operation(state, authenticated_customer_id=customer_id,
                                                  payment_code=code)
        patch.update(response("La operación está preparada únicamente en el estado conversacional. La escritura está deshabilitada hasta asegurar su checkpoint durable previo y recuperación. No se ha registrado ni recibido un pago, ni emitido una factura fiscal."))
        return patch
    except (ValueError, LookupError, KeyError, TypeError):
        return response("No fue posible validar la identidad, la cotización o la operación pendiente. Se requiere revisión; no se ha creado una orden de pago.")
    except Exception:
        return response("No fue posible consultar los registros financieros. No se ha creado una orden de pago; intenta nuevamente cuando el almacenamiento esté disponible.")
