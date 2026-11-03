"""Patrón de referencia del chat: implementa el contrato común con un grafo LangGraph determinista.

Sirve para probar el frontend y la sesión sin depender de Groq. Los patrones del equipo reemplazan el grafo
por el suyo y mantienen la ruta, la dependencia de sesión y el formato de respuesta.

Ejecutar:  uvicorn app.chat.reference:create_reference_app --factory --host localhost --port 8001
"""
import logging
import secrets
import threading
import uuid
from typing import TypedDict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langgraph.graph import END, START, StateGraph
from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.accounts.api import _validation_response
from app.accounts.config import Settings
from app.accounts.security import LoginLimiter
from app.accounts.session import SessionCustomer, SessionGuard
from app.agents.sales import build_sales_graph
from app.chat.contract import ChatIn, ChatOut, QuoteLine, QuoteOut, TicketOut
from app.chat.models import Ticket, TicketStatus

logger = logging.getLogger(__name__)

# Palabras clave del cliente: el chat es en español, por eso los términos se buscan en español.
STORAGE_WORDS = ("ssd", "disco", "almacenamiento", "no detecta", "lento", "lentitud")


class ChatState(TypedDict, total=False):
    message: str
    name: str
    diagnosis: str
    items: list[dict]
    quote: dict
    reply: str


def attention(state: ChatState) -> dict:
    """Agente de atención: pide más datos si el mensaje no describe equipo y síntoma."""
    if len(state["message"].split()) < 4:
        return {
            "reply": (
                f"Hola {state['name']}. Soy TechFix Copilot. Puedo orientarte con "
                "soporte y reparaciones, consultar componentes y cotizaciones, "
                "ayudarte a armar una PC según tu presupuesto y responder consultas "
                "de garantía o logística. ¿Qué necesitas hoy?"
            )
        }
    return {}


def technical_support(state: ChatState) -> dict:
    """Agente técnico de referencia: diagnóstico provisional por palabras clave."""
    text = state["message"].lower()
    if any(word in text for word in STORAGE_WORDS):
        return {"diagnosis": "Posible falla de la unidad de almacenamiento.",
                "items": [{"code": "instalacion_ssd"}, {"code": "ssd_480"}]}
    return {"diagnosis": "Se requiere una revisión técnica presencial.", "items": [{"code": "revision"}]}


def build_reference_graph(sales_graph=None):
    sales_graph = sales_graph or build_sales_graph()

    def sales(state: ChatState) -> dict:
        request = {"equipment": state["message"][:200], "diagnosis": state["diagnosis"], "items": state["items"]}
        return {"quote": sales_graph.invoke({"request": request})["quote"]}

    builder = StateGraph(ChatState)
    builder.add_node("attention", attention)
    builder.add_node("technical_support", technical_support)
    builder.add_node("sales", sales)
    builder.add_edge(START, "attention")
    builder.add_conditional_edges("attention", lambda s: END if s.get("reply") else "technical_support")
    builder.add_edge("technical_support", "sales")
    builder.add_edge("sales", END)
    return builder.compile(name="chat_reference_graph")


def _quote_lines(quote: dict) -> list[QuoteLine]:
    lines = []
    for item in quote.get("labor", []) + quote.get("parts", []):
        label = item["description"] if item["quantity"] == 1 else f"{item['description']} × {item['quantity']}"
        lines.append(QuoteLine(label=label, amount=item["amount"]))
    return lines


def create_reference_app(settings: Settings | None = None, session_factory: sessionmaker | None = None) -> FastAPI:
    load_dotenv()
    guard = SessionGuard(settings, session_factory) if settings and session_factory else SessionGuard.from_env(session_factory)
    factory = guard.session_factory

    app = FastAPI(title="TechFix.AI · Chat de referencia", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(guard.settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["POST"],
        allow_headers=["Content-Type", "Accept"],
    )
    guard.install(app)
    graph = build_reference_graph()
    limiter = LoginLimiter(20, 60)
    conversations: dict[str, dict] = {}
    lock = threading.Lock()

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_request: Request, exc: RequestValidationError):
        return _validation_response(exc)

    @app.exception_handler(OperationalError)
    async def on_db_unavailable(_request: Request, _exc: OperationalError):
        logger.error("Database unavailable")
        return JSONResponse(status_code=503, content={"detail": "El asistente no está disponible. Inténtalo en unos minutos."})

    def set_ticket_status(ticket_id: int, customer_id: int, status: TicketStatus) -> None:
        with factory() as db:
            db.execute(update(Ticket).where(Ticket.id == ticket_id, Ticket.customer_id == customer_id).values(status=status))
            db.commit()

    @app.post("/api/chat", response_model=ChatOut, response_model_exclude_none=True)
    def chat(body: ChatIn, customer: SessionCustomer = Depends(guard.require_customer)):
        key = str(customer.id)
        if limiter.blocked(key):
            return JSONResponse(status_code=429, content={"detail": "Enviaste muchos mensajes seguidos. Espera un minuto."})
        limiter.fail(key)

        with lock:
            if body.conversation_id:
                conv = conversations.get(body.conversation_id)
                # Igual respuesta si no existe o es de otro cliente.
                if conv is None or conv["customer_id"] != customer.id:
                    return JSONResponse(status_code=404, content={"detail": "Conversación no encontrada."})
                conversation_id = body.conversation_id
            else:
                conversation_id = str(uuid.uuid4())
                conv = conversations[conversation_id] = {"customer_id": customer.id, "quote": None, "ticket": None}

        quote: QuoteOut | None = conv["quote"]
        ticket: TicketOut | None = conv["ticket"]

        if body.action:
            if quote is None or quote.status != "proposed":
                return JSONResponse(status_code=409, content={"detail": "No hay un presupuesto pendiente en esta conversación."})
            accepted = body.action == "accept_quote"
            new_status = TicketStatus.IN_REPAIR if accepted else TicketStatus.CANCELLED
            set_ticket_status(conv["ticket_id"], customer.id, new_status)
            conv["quote"] = quote = quote.model_copy(update={"status": "confirmed" if accepted else "rejected"})
            conv["ticket"] = ticket = TicketOut(code=ticket.code, status=new_status.value)
            reply = (f"Listo, registré tu aprobación. El ticket {ticket.code} pasó a reparación."
                     if accepted else f"Entendido, rechazaste el presupuesto. Cerré el ticket {ticket.code}.")
            return ChatOut(conversation_id=conversation_id, reply=reply, quote=quote, ticket=ticket)

        if quote is not None and quote.status == "proposed":
            return ChatOut(conversation_id=conversation_id, quote=quote, ticket=ticket,
                           reply="Tienes un presupuesto pendiente. Acéptalo o recházalo para continuar.")

        result = graph.invoke({"message": body.message, "name": customer.first_name})
        if result.get("reply"):
            return ChatOut(conversation_id=conversation_id, reply=result["reply"])

        sales = result["quote"]
        quote = QuoteOut(status="proposed", lines=_quote_lines(sales), total=sales["total"] or sales["known_subtotal"])
        with factory() as db:
            row = Ticket(code=f"TCK-{secrets.token_hex(3).upper()}", customer_id=customer.id,
                         title=f"Consulta: {body.message[:180]}", failure_description=body.message,
                         status=TicketStatus.QUOTED, provisional_diagnosis=result["diagnosis"])
            db.add(row)
            db.commit()
            ticket = TicketOut(code=row.code, status=TicketStatus.QUOTED.value)
            conv.update(quote=quote, ticket=ticket, ticket_id=row.id)

        reply = (f"Gracias, {customer.first_name}. Diagnóstico provisional: {result['diagnosis']} "
                 f"Registré el ticket {ticket.code} y preparé este presupuesto con el catálogo de prueba. "
                 "Revísalo y acéptalo para iniciar la reparación.")
        return ChatOut(conversation_id=conversation_id, reply=reply, quote=quote, ticket=ticket)

    return app
