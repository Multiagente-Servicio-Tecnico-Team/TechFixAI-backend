from typing import Annotated, Any
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    # Historial compartido entre agentes
    messages: Annotated[list[AnyMessage], add_messages]
    customer_id: int
    conversation_id: str

    # Inicio del turno actual, para no confundir herramientas de turnos anteriores.
    turn_start_index: int
    quote_scope: str
    quote_type: str
    quote_task_type: str
    quote_status: str
    quote: dict[str, Any]
    ticket_id: int
    ticket_code: str
    ticket_status: str
    payment_code: str
    awaiting_refund_details: bool
    refund_id: int
    refund_status: str
    outcome: str
    inventory_query: str | None

    # Agente actual y siguiente
    current_agent: str
    next_agent: str | None

    # Control de transferencias
    handoff_history: list[dict[str, Any]]
    handoff_count: int

    # Control de herramientas
    tool_iterations: dict[str, int]

    # Repuestos identificados para la reparación
    required_parts: list[dict[str, Any]]

    # Indica si falta verificar el inventario
    inventory_pending: bool

    # Resultados obtenidos de PostgreSQL
    inventory_results: list[dict[str, Any]]

    # Errores registrados
    errors: list[str]
