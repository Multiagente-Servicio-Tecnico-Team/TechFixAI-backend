from typing import Annotated, Any

from langgraph.prebuilt import InjectedState
from langchain_core.tools import tool

from app.application.catalog import CatalogService
from app.application.ports import CustomerContext
from app.adapters.tools.catalog import make_catalog_lookup_tool
from app.database.repository import ServiceRepository
from app.agents.decentralized.state import AgentState

catalog_service = CatalogService(ServiceRepository())


@tool
def consultar_inventario(
    nombre_repuesto: str,
    state: Annotated[AgentState, InjectedState()],
    cantidad: int = 1,
) -> dict[str, object]:
    """Consulta PostgreSQL con la identidad autenticada inyectada por LangGraph."""
    context = CustomerContext(
        customer_id=state["customer_id"],
        conversation_id=state.get("conversation_id", ""),
        pattern_id="decentralized",
    )
    tool = make_catalog_lookup_tool(catalog_service, customer_context=context)
    return tool.invoke({"requested_name": nombre_repuesto, "quantity": cantidad})

@tool
def transferir_a_ventas(motivo: str) -> str:
    """Transfiere a Ventas los resultados del inventario."""
    return f"TRANSFERIR_VENTAS: {motivo}"
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".warehouse_tools", __package__)
