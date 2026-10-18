"""Authenticated chat API for selecting and tracing the LangGraph patterns."""

import logging
from contextlib import AbstractContextManager, nullcontext, asynccontextmanager
from threading import Lock, RLock
from typing import Any, Callable
from uuid import uuid4
from pathlib import Path

from dotenv import load_dotenv

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import APIError as GroqAPIError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage
from langsmith import Client, tracing_context
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.api import _validation_response
from app.accounts.config import Settings as AccountSettings
from app.accounts.security import LoginLimiter
from app.accounts.session import (
    SessionCustomer,
    SessionError,
    SessionGuard,
)
from app.chat.contract import ChatIn, ChatOut, QuoteLine, QuoteOut, TicketOut
from app.settings import Settings, load_settings
from app.database.conversation_owners import (
    ConversationOwnersRepository, ConversationNotFound, ConversationConflict,
    ConversationStorageError,
)
from app.database.conversation_locks import ConversationLocks, ConversationBusy, ConversationLockStorageError


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PATTERN_NAMES = {
    "hierarchical": "Jerárquico",
    "orchestrator": "Orquestador / supervisor",
    "decentralized": "Red descentralizada",
}
GraphFactory = Callable[[], Any]


def get_trace_context(
    settings: Settings | None = None,
) -> AbstractContextManager[None]:
    settings = settings or load_settings()
    if not settings.langsmith_tracing:
        return nullcontext()
    if not settings.langsmith_api_key:
        raise RuntimeError(
            "LANGSMITH_API_KEY es necesaria cuando LANGSMITH_TRACING=true."
        )
    client = Client(
        api_key=settings.langsmith_api_key,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
        anonymizer=redact_trace_error,
    )
    return tracing_context(
        enabled=True,
        project_name=settings.langsmith_project,
        client=client,
    )


def redact_trace_error(values: dict[str, Any]) -> dict[str, Any]:
    if isinstance(values.get("error"), str):
        return {**values, "error": "Provider error details redacted."}
    return values


def _build_hierarchical_graph() -> Any:
    from app.agents.jerarquico.graph.builder import build_multiagent_graph

    settings = load_settings()
    settings.require_chat_configuration()
    return build_multiagent_graph(settings=settings)


def _build_orchestrator_graph() -> Any:
    from app.agents.orquestador import build_graph

    return build_graph()


def _build_decentralized_graph(checkpointer, *, financial_repository=None) -> Any:
    from app.agents.decentralized.graph import build_graph
    from app.database.decentralized_repository import DecentralizedRepository

    return build_graph(checkpointer=checkpointer, ticket_writes=True, financial_repository=(
        financial_repository if financial_repository is not None else DecentralizedRepository()))


def _checkpoint_resources(settings):
    from app.database.decentralized_checkpoint import build_checkpoint_resources
    return build_checkpoint_resources(settings)


def _message_for_action(action: str | None, message: str | None) -> str:
    if action == "accept_quote":
        return "Sí, confirmo"
    if action == "reject_quote":
        return "No, rechazo el presupuesto"
    return message or ""


def _as_decimal_text(value: Any) -> str:
    return f"{value:.2f}" if hasattr(value, "__format__") else str(value)


def _quote_for_result(pattern: str, result: dict[str, Any]) -> QuoteOut | None:
    status: str | None = None
    lines: list[QuoteLine] = []
    total: Any = None

    if pattern == "hierarchical":
        quote = result.get("quote")
        if result.get("outcome") == "awaiting_confirmation":
            status = "proposed"
        elif result.get("outcome") == "quoted":
            status = "saved"
        elif result.get("outcome") == "declined":
            status = "rejected"
        if quote and status:
            task_type = quote.get("labor_task_type", "maintenance")
            labor_name = (
                "Diagnóstico técnico"
                if task_type == "diagnosis"
                else "Mano de obra"
            )
            lines.append(
                QuoteLine(
                    label=labor_name,
                    amount=_as_decimal_text(quote["labor_cost"]),
                )
            )
            lines.extend(
                QuoteLine(
                    label=(
                        f"{part['name']} × {part['quantity']}"
                    ),
                    amount=_as_decimal_text(part["subtotal"]),
                )
                for part in quote.get("parts", [])
            )
            total = quote["total_amount"]

    elif pattern == "orchestrator":
        if result.get("awaiting_ticket_confirmation"):
            status = "proposed"
        elif result.get("ticket_cancelled"):
            status = "rejected"
        elif result.get("quote_id") is not None:
            status = "saved"
        if status:
            task_type = result.get("labor_task_type", "maintenance")
            labor_name = (
                "Diagnóstico técnico"
                if task_type == "diagnosis"
                else "Mano de obra"
            )
            lines.append(
                QuoteLine(
                    label=labor_name,
                    amount=_as_decimal_text(result.get("labor_cost", 0)),
                )
            )
            lines.extend(
                QuoteLine(
                    label=f"{part['name']} × {part['quantity']}",
                    amount=_as_decimal_text(
                        part["unit_price"] * int(part["quantity"])
                    ),
                )
                for part in result.get("available_parts", [])
            )
            total = result.get("total")

    if status is None or total is None:
        return None
    return QuoteOut(
        status=status,
        lines=lines,
        total=_as_decimal_text(total),
    )


def _reply_for_result(pattern: str, result: dict[str, Any]) -> str:
    if pattern == "orchestrator":
        reply = result.get("response")
        if isinstance(reply, str) and reply.strip():
            return reply
    messages = result.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        content = messages[-1].content
        if isinstance(content, str) and content.strip():
            return content
    if messages and isinstance(messages[-1].content, str):
        return messages[-1].content
    raise ValueError("El patrón no produjo una respuesta de chat.")


def _ticket_for_result(pattern: str, result: dict[str, Any]) -> TicketOut | None:
    if pattern == "decentralized":
        if type(result.get("ticket_id")) is int and result["ticket_id"] > 0 and result.get("ticket_code") and result.get("ticket_status"):
            return TicketOut(code=result["ticket_code"], status=result["ticket_status"])
        return None
    if pattern == "hierarchical" and result.get("outcome") == "quoted":
        code = result.get("ticket_code")
    elif pattern == "orchestrator" and result.get("quote_id") is not None:
        code = result.get("ticket_code")
    else:
        return None
    if not isinstance(code, str) or not code:
        return None
    return TicketOut(code=code, status="QUOTED")


def create_app(
    *,
    session_guard: SessionGuard | None = None,
    graph_factories: dict[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: Callable[[], AbstractContextManager[None]] | None = None,
    checkpoint_resources_factory: Callable[[], Any] | None = None,
    conversation_owners_repository: Any | None = None,
    conversation_locks: Any | None = None,
    financial_repository: Any | None = None,
) -> FastAPI:
    # Read the project file before account settings or technical resources.
    # Externally supplied configuration remains authoritative.
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

    @asynccontextmanager
    async def lifespan(application):
        resources = None
        try:
            if graph_factories is None:
                stage = "configuration"
                try:
                    if checkpoint_resources_factory is None:
                        from app.database.decentralized_checkpoint import load_checkpoint_settings
                        checkpoint_settings = load_checkpoint_settings()
                        stage = "pool_construction"
                        resources = _checkpoint_resources(checkpoint_settings)
                    else:
                        stage = "pool_construction"
                        resources = checkpoint_resources_factory()
                    stage = "pool_open"
                    resources.pool.open(wait=True)
                    stage = "graph_construction"
                    if financial_repository is None:
                        application.state.decentralized_graph = _build_decentralized_graph(resources.saver)
                    else:
                        application.state.decentralized_graph = _build_decentralized_graph(
                            resources.saver, financial_repository=financial_repository)
                    stage = "resource_association"
                    application.state.checkpoint_resources = resources
                    application.state.conversation_owners = ConversationOwnersRepository(resources.pool)
                    if resources.pool.max_size < 2:
                        raise RuntimeError("Pool requiere capacidad para coordinación y saver")
                    application.state.conversation_locks = ConversationLocks(resources.pool)
                except Exception as exc:
                    logger.error("Decentralized checkpoint initialization failed; stage=%s; type=%s",
                                 stage, type(exc).__name__)
                    if resources is not None:
                        try:
                            resources.close()
                        except Exception:
                            logger.error("Decentralized checkpoint cleanup failed")
                        resources = None
                    application.state.decentralized_graph = None
            yield
        finally:
            application.state.decentralized_graph = None
            application.state.checkpoint_resources = None
            application.state.conversation_owners = None
            application.state.conversation_locks = None
            graph_cache.pop("decentralized", None)
            if resources is not None:
                try:
                    resources.close()
                except Exception:
                    logger.error("Decentralized checkpoint shutdown failed")

    app = FastAPI(title="TechFix.AI · Patrones LangGraph", version="1.1.0", lifespan=lifespan)
    app.state.decentralized_graph = None
    app.state.checkpoint_resources = None
    app.state.conversation_owners = conversation_owners_repository
    app.state.conversation_locks = conversation_locks
    account_settings = (
        session_guard.settings
        if session_guard is not None
        else AccountSettings.from_env()
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(account_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.add_exception_handler(SessionError, lambda _request, exc: JSONResponse(
        status_code=exc.status,
        content={"detail": exc.detail, "code": exc.code},
    ))
    app.add_exception_handler(
        RequestValidationError,
        lambda _request, exc: _validation_response(exc),
    )

    graph_builders = graph_factories or {
        "hierarchical": _build_hierarchical_graph,
        "orchestrator": _build_orchestrator_graph,
        "decentralized": lambda: app.state.decentralized_graph,
    }
    if set(graph_builders) != set(PATTERN_NAMES):
        raise ValueError("Debe configurarse exactamente cada patrón disponible.")

    graph_cache: dict[str, Any] = {}
    conversations: dict[str, dict[str, Any]] = {}
    conversations_lock = RLock()
    limiter = LoginLimiter(20, 60)

    def get_guard() -> SessionGuard:
        nonlocal session_guard
        if session_guard is None:
            session_guard = SessionGuard.from_env()
        return session_guard

    def require_customer(request: Request) -> SessionCustomer:
        return get_guard().require_customer(request)

    def get_graph(pattern: str) -> Any:
        with conversations_lock:
            if pattern == "decentralized" and graph_factories is None:
                graph = app.state.decentralized_graph
                if graph is None:
                    raise HTTPException(status_code=503, detail="El almacenamiento del asistente no está disponible.")
                return graph
            if pattern not in graph_cache:
                graph_cache[pattern] = graph_builders[pattern]()
            return graph_cache[pattern]

    def invoke_pattern(
        pattern: str,
        conversation_id: str,
        customer: SessionCustomer,
        message: str,
        thread_id: str | None = None,
        resume_payment: bool = False,
        resume_logistics: bool = False,
        resume_warranty: bool = False,
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

        config = {
            "configurable": {"thread_id": thread_id or conversation_id},
            "run_name": f"techfix-{pattern}",
            "tags": ["service-chat", f"pattern:{pattern}"],
            "metadata": {
                "pattern": pattern,
                "conversation_id": conversation_id,
            },
        }
        with (trace_context_factory or (lambda: get_trace_context(settings_factory())))():
            graph = get_graph(pattern)
            if pattern == "decentralized" and (graph_factories is None or financial_repository is not None):
                from psycopg import Error as PsycopgError
                from app.agents.decentralized.payment_operations import validate_pending_payment_operation
                from app.agents.decentralized.logistics_operations import validate_pending_logistics_operation
                try:
                    snapshot = graph.get_state(config)
                    saved = snapshot.values
                    if saved and saved.get("customer_id") != customer.id:
                        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
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
                            raise HTTPException(status_code=409, detail=(
                                "La operación quedó bloqueada por una corrección y necesita reconciliación. No se intentará otra escritura."
                                if blocked else "Hay una solicitud preparada. Responde continuar para registrar esa misma solicitud."))
                        return graph.invoke(None, config=config,
                            context={"authenticated_customer_id": customer.id}, durability="sync")
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
                            raise HTTPException(status_code=409, detail="No hay reclamo pendiente de reanudación.")
                        state = None
                    elif not resume_logistics and not resume_payment and "ejecutar_garantia" in snapshot.next:
                        raise HTTPException(status_code=409, detail="El reclamo requiere reanudación explícita.")
                    elif resume_logistics:
                        if logistics_pending is None or "ejecutar_logistica" not in snapshot.next:
                            raise HTTPException(status_code=409, detail="No hay una operación logística pendiente de reanudación.")
                        state = None
                    elif resume_payment:
                        if pending is None or "ejecutar_pago" not in snapshot.next:
                            raise HTTPException(status_code=409, detail="No hay una operación financiera pendiente de reanudación.")
                        state = None
                    elif "ejecutar_logistica" in snapshot.next:
                        raise HTTPException(status_code=409, detail="La operación logística requiere reanudación explícita.")
                    elif "ejecutar_pago" in snapshot.next:
                        raise HTTPException(status_code=409, detail="La operación financiera requiere reanudación explícita.")
                    return graph.invoke(state, config=config,
                        context={"authenticated_customer_id": customer.id}, durability="sync")
                except PsycopgError:
                    raise HTTPException(status_code=503, detail="El almacenamiento del asistente no está disponible.") from None
            return graph.invoke(state, config=config)

    @app.get("/api/chat/patterns")
    def patterns(_customer: SessionCustomer = Depends(require_customer)):
        return {
            "patterns": [
                {"id": pattern_id, "name": name}
                for pattern_id, name in PATTERN_NAMES.items()
            ]
        }

    @app.post("/api/chat", response_model=ChatOut, response_model_exclude_none=True)
    def chat(
        body: ChatIn,
        customer: SessionCustomer = Depends(require_customer),
    ) -> ChatOut:
        customer_key = str(customer.id)
        if limiter.blocked(customer_key):
            return JSONResponse(
                status_code=429,
                content={"detail": "Enviaste muchos mensajes seguidos. Espera un minuto."},
            )
        limiter.fail(customer_key)

        is_new = body.conversation_id is None
        conversation_id = body.conversation_id or str(uuid4())
        thread_id = conversation_id
        if body.pattern == "decentralized":
            # Memory holds only a local lock, never ownership authority.
            repository = conversation_owners_repository or app.state.conversation_owners
            if repository is None:
                raise HTTPException(status_code=503, detail="El almacenamiento del asistente no está disponible.")
            with conversations_lock:
                local = conversations.get(conversation_id)
                if local and local["pattern"] != body.pattern and local["customer_id"] == customer.id:
                    return JSONResponse(status_code=409, content={"detail": "Para cambiar de patrón, inicia una conversación nueva.", "code": "pattern_locked"})
            try:
                if is_new:
                    owner = repository.register(conversation_id=conversation_id, thread_id=conversation_id,
                                                authenticated_customer_id=customer.id)
                else:
                    owner = repository.authorize(conversation_id=conversation_id,
                                                 authenticated_customer_id=customer.id)
                thread_id = owner["thread_id"]
            except ConversationNotFound:
                return JSONResponse(status_code=404, content={"detail": "Conversación no encontrada.", "code": "not_found"})
            except ConversationConflict:
                return JSONResponse(status_code=409, content={"detail": "Para cambiar de patrón, inicia una conversación nueva.", "code": "pattern_locked"})
            except ConversationStorageError:
                raise HTTPException(status_code=503, detail="El almacenamiento del asistente no está disponible.") from None
        with conversations_lock:
            conversation = conversations.get(conversation_id)
            if (not is_new and conversation is None and body.pattern != "decentralized"
                    and (conversation_owners_repository or app.state.conversation_owners) is not None):
                try:
                    (conversation_owners_repository or app.state.conversation_owners).authorize(
                        conversation_id=conversation_id, authenticated_customer_id=customer.id)
                except ConversationNotFound:
                    pass
                except ConversationConflict:
                    return JSONResponse(status_code=409, content={"detail": "Para cambiar de patrón, inicia una conversación nueva.", "code": "pattern_locked"})
                except ConversationStorageError:
                    raise HTTPException(status_code=503, detail="El almacenamiento del asistente no está disponible.") from None
                else:
                    return JSONResponse(status_code=409, content={"detail": "Para cambiar de patrón, inicia una conversación nueva.", "code": "pattern_locked"})
            if is_new or (body.pattern == "decentralized" and conversation is None):
                conversation = {
                    "customer_id": customer.id,
                    "pattern": body.pattern,
                    "pending_quote": False,
                    "lock": Lock(),
                }
                conversations[conversation_id] = conversation
            elif (
                conversation is None
                or conversation["customer_id"] != customer.id
            ):
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Conversación no encontrada.", "code": "not_found"},
                )
            elif conversation["pattern"] != body.pattern:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Para cambiar de patrón, inicia una conversación nueva.",
                        "code": "pattern_locked",
                    },
                )

        assert conversation is not None
        if body.action in {"resume_payment", "resume_logistics", "resume_warranty"} and body.pattern != "decentralized":
            raise HTTPException(status_code=409, detail="Acción no disponible para este patrón.")
        if body.action and body.action not in {"resume_payment", "resume_logistics", "resume_warranty"} and (
            body.pattern == "decentralized"
            or not conversation["pending_quote"]
        ):
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "No hay un presupuesto pendiente en esta conversación.",
                    "code": "no_quote",
                },
            )
        message = _message_for_action(body.action, body.message)

        # Authorization above precedes lock acquisition. Independent threads use
        # independent advisory keys; only the decentralized branch uses PostgreSQL.
        coordination = nullcontext()
        if body.pattern == "decentralized":
            locks = conversation_locks or app.state.conversation_locks
            if locks is None:
                raise HTTPException(status_code=503, detail="La coordinación del asistente no está disponible.")
            coordination = locks.hold(thread_id)
        try:
            with coordination:
                return run_conversation(body, customer, conversation_id, thread_id, conversation, message)
        except ConversationBusy:
            return JSONResponse(status_code=409, content={"detail": "La conversación está procesando otro mensaje.", "code": "conversation_busy"})
        except ConversationLockStorageError:
            raise HTTPException(status_code=503, detail="La coordinación del asistente no está disponible.") from None

    def run_conversation(body, customer, conversation_id, thread_id, conversation, message):
        with conversation["lock"]:
            try:
                result = invoke_pattern(
                    body.pattern,
                    conversation_id,
                    customer,
                    message,
                    thread_id=thread_id,
                    resume_payment=body.action == "resume_payment",
                    resume_logistics=body.action == "resume_logistics",
                    resume_warranty=body.action == "resume_warranty",
                )
            except (SQLAlchemyError, OSError) as exc:
                logger.error(
                    "Pattern database or storage operation failed: %s",
                    type(exc).__name__,
                )
                raise HTTPException(
                    status_code=503,
                    detail="El asistente no pudo completar la operación.",
                ) from exc
            except GroqAPIError as exc:
                logger.error("Groq request failed: %s", type(exc).__name__)
                raise HTTPException(
                    status_code=502,
                    detail="El proveedor LLM no pudo procesar el mensaje.",
                ) from exc
            except (OutputParserException, ValidationError, ValueError, LookupError, RuntimeError) as exc:
                logger.error("Pattern processing failed: %s", type(exc).__name__)
                raise HTTPException(
                    status_code=502,
                    detail="El patrón no pudo completar el mensaje.",
                ) from exc

            quote = _quote_for_result(body.pattern, result)
            if body.pattern == "hierarchical":
                conversation["pending_quote"] = (
                    result.get("outcome") == "awaiting_confirmation"
                )
            elif body.pattern == "orchestrator":
                conversation["pending_quote"] = bool(
                    result.get("awaiting_ticket_confirmation")
                )
            answer = _reply_for_result(body.pattern, result)
            return ChatOut(
                conversation_id=conversation_id,
                reply=answer,
                quote=quote,
                ticket=_ticket_for_result(body.pattern, result),
                pattern=body.pattern,
            )

    return app


app = create_app()
