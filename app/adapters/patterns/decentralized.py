"""Nine-role decentralized adapter over the shared application contracts."""
from typing import Any
from langchain_core.messages import HumanMessage
from app.accounts.session import SessionCustomer
from app.adapters.patterns.decentralized_legacy_reply import LegacyReplyPattern
from app.adapters.patterns.base import last_message_text
from app.adapters.llm.tracing import get_trace_context
from app.application.errors import ConversationActionError
from app.domain.chat import PatternReply, Quote, QuoteLine, TicketRef

def _build_decentralized_graph(checkpointer, *, financial_repository=None) -> Any:
    from app.agents.decentralized.graph import build_graph
    from app.database.decentralized_repository import DecentralizedRepository

    return build_graph(checkpointer=checkpointer, ticket_writes=True, quote_writes=True, financial_repository=(
        financial_repository if financial_repository is not None else DecentralizedRepository()))

def build_invoker(get_graph, graph_factories, financial_repository, trace_context_factory, settings_factory, config_factory,
                  accounting_service_factory=None):
    def invoke_pattern(
        pattern: str,
        conversation_id: str,
        customer: SessionCustomer,
        message: str,
        thread_id: str | None = None,
        resume_payment: bool = False,
        resume_logistics: bool = False,
        resume_warranty: bool = False,
        quote_action: str | None = None,
        proposal_id: str | None = None,
    ) -> dict[str, Any]:
        from app.agents.orquestador.graph.state import AgentState as OrchestratorState
        from app.agents.jerarquico.graph.state import ServiceState
        from app.agents.decentralized.state import AgentState as DecentralizedState

        human_message = HumanMessage(content=message)
        if pattern == "hierarchical":
            state: ServiceState = {
                "messages": [human_message],
                "customer_id": customer.id,
            }
        elif pattern == "orchestrator":
            state = OrchestratorState(
                messages=[human_message],
                user_id=customer.id,
            )
        else:
            state = DecentralizedState(messages=[human_message], customer_id=customer.id)
            if getattr(customer, "role", None) == "ADMIN":
                state["current_agent"] = "contador"

        config = config_factory(conversation_id)
        config["configurable"]["thread_id"] = thread_id or conversation_id
        config["configurable"]["conversation_id"] = conversation_id
        context = {"authenticated_customer_id": customer.id, "authenticated_role": getattr(customer, "role", None),
                   "accounting_service_factory": accounting_service_factory}
        with (trace_context_factory or (lambda: get_trace_context(settings_factory())))():
            graph = get_graph(pattern)
            if pattern == "decentralized" and quote_action is not None:
                from psycopg import Error as PsycopgError
                from app.agents.decentralized.quote_operations import apply_quote_action, QuoteConflict
                try:
                    return apply_quote_action(graph, config, authenticated_customer_id=customer.id,
                        conversation_id=conversation_id, proposal_id=proposal_id, action=quote_action)
                except QuoteConflict as exc:
                    raise ConversationActionError(status_code=409, detail=str(exc)) from None
                except (ValueError, LookupError):
                    raise ConversationActionError(status_code=409, detail="No se pudo validar la propuesta y su propietario. Consulta una propuesta vigente.") from None
                except PsycopgError:
                    raise ConversationActionError(status_code=503, detail="El almacenamiento del asistente no está disponible.") from None
            if pattern == "decentralized" and (graph_factories is None or financial_repository is not None):
                from psycopg import Error as PsycopgError
                from app.agents.decentralized.payment_operations import validate_pending_payment_operation
                from app.agents.decentralized.logistics_operations import validate_pending_logistics_operation
                try:
                    snapshot = graph.get_state(config)
                    saved = snapshot.values
                    if saved and saved.get("customer_id") != customer.id:
                        raise ConversationActionError(status_code=404, detail="Conversación no encontrada.")
                    from app.agents.decentralized.quote_operations import quote_requires_retry
                    if quote_requires_retry(graph, config, snapshot):
                        raise ConversationActionError(status_code=409, detail="Hay una cotización pendiente. Reintenta su aceptación sin cambiar la propuesta.")
                    if "ejecutar_ticket" in snapshot.next:
                        from app.agents.decentralized.ticket_operations import validate_pending_ticket_operation
                        from app.agents.decentralized.policy import normalize_text
                        validate_pending_ticket_operation(saved.get("pending_ticket_operation"),
                            authenticated_customer_id=customer.id, request_revision=saved.get("request_revision"))
                        if saved.get("ticket_correction_required") or normalize_text(message).strip(" .!¿?¡") not in {
                                "continuar", "continua", "confirmo", "registrar", "reintentar", "reintento", "si"}:
                            from app.agents.decentralized.ticket_intake import classify_request
                            blocked = saved.get("ticket_correction_required") or classify_request(message) not in {"INFO_QUERY", "WARRANTY_STATUS_CHECK"}
                            if blocked:
                                graph.update_state(config, {"ticket_correction_required": True})
                            raise ConversationActionError(status_code=409, detail=(
                                "La operación quedó bloqueada por una corrección y necesita reconciliación. No se intentará otra escritura."
                                if blocked else "Hay una solicitud preparada. Responde continuar para registrar esa misma solicitud."))
                        return graph.invoke(None, config=config,
                            context=context, durability="sync")
                    pending = saved.get("pending_payment_operation") if saved else None
                    logistics_pending = saved.get("pending_logistics_operation") if saved else None
                    if logistics_pending is not None:
                        validate_pending_logistics_operation(logistics_pending,
                            authenticated_customer_id=customer.id, request_revision=saved.get("request_revision"))
                    if pending is not None:
                        validate_pending_payment_operation(pending, authenticated_customer_id=customer.id,
                                                           request_revision=saved.get("request_revision"))
                    from app.agents.decentralized.warranty_operations import validate_pending_warranty_operation
                    warranty_pending = saved.get("pending_warranty_operation") if saved else None
                    if warranty_pending is not None:
                        validate_pending_warranty_operation(warranty_pending, authenticated_customer_id=customer.id, request_revision=saved.get("request_revision"))
                    if resume_warranty:
                        if warranty_pending is None or "ejecutar_garantia" not in snapshot.next:
                            raise ConversationActionError(status_code=409, detail="No hay reclamo pendiente de reanudación.")
                        state = None
                    elif not resume_logistics and not resume_payment and "ejecutar_garantia" in snapshot.next:
                        raise ConversationActionError(status_code=409, detail="El reclamo requiere reanudación explícita.")
                    elif resume_logistics:
                        if logistics_pending is None or "ejecutar_logistica" not in snapshot.next:
                            raise ConversationActionError(status_code=409, detail="No hay una operación logística pendiente de reanudación.")
                        state = None
                    elif resume_payment:
                        if pending is None or "ejecutar_pago" not in snapshot.next:
                            raise ConversationActionError(status_code=409, detail="No hay una operación financiera pendiente de reanudación.")
                        state = None
                    elif "ejecutar_logistica" in snapshot.next:
                        raise ConversationActionError(status_code=409, detail="La operación logística requiere reanudación explícita.")
                    elif "ejecutar_pago" in snapshot.next:
                        raise ConversationActionError(status_code=409, detail="La operación financiera requiere reanudación explícita.")
                    return graph.invoke(state, config=config,
                        context=context, durability="sync")
                except PsycopgError:
                    raise ConversationActionError(status_code=503, detail="El almacenamiento del asistente no está disponible.") from None
            return graph.invoke(state, config=config, context=context) if pattern == "decentralized" else graph.invoke(state, config=config)
    return invoke_pattern

class DecentralizedPattern(LegacyReplyPattern):
    def build_graph(self):
        raise RuntimeError("La red requiere PostgresSaver inicializado por infraestructura.")

    def configure_runtime(self, *, graph_factories, financial_repository, accounting_service_factory=None):
        self.invoke_turn = build_invoker(lambda pattern: self.graph(), graph_factories,
            financial_repository, self._trace_context_factory, self._settings_factory, self.config,
            accounting_service_factory=accounting_service_factory)

    def to_reply(self, result):
        if not result.get("proposal"):
            reply = super().to_reply(result)
            if result.get("ticket_id") and result.get("ticket_code") and result.get("ticket_status"):
                from dataclasses import replace
                reply = replace(reply, ticket=TicketRef(result["ticket_code"], result["ticket_status"]))
            return reply
        from app.agents.decentralized.quote_operations import quote_response
        data = quote_response(result)
        quote = None if data is None else Quote(status=data["status"], total=data["total"],
            currency=data["currency"], proposal_id=data["proposal_id"],
            lines=tuple(QuoteLine(**line) for line in data["lines"]))
        ticket = TicketRef(result["ticket_code"], result["ticket_status"]) if result.get("ticket_id") and result.get("ticket_code") else None
        return PatternReply(last_message_text(result), quote, ticket, bool(quote and quote.is_pending))
