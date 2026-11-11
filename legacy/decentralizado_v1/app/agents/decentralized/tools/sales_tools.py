from typing import Annotated
import unicodedata

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.adapters.tools.quotes import QuotePartInput, make_quote_calculation_tool
from app.agents.decentralized.state import AgentState
from app.application.catalog import CatalogService
from app.application.pc_builds import available_pc_builds, modify_pc_build
from app.application.ports import CustomerContext
from app.database.repository import ServiceRepository
from app.settings import load_settings

catalog_service = CatalogService(ServiceRepository())

_MISSING_SERVICE = object()


def normalize_service(service=_MISSING_SERVICE, *, servicio=_MISSING_SERVICE) -> str:
    if service is _MISSING_SERVICE:
        if servicio is _MISSING_SERVICE:
            raise TypeError("Missing service")
        service = servicio
    elif servicio is not _MISSING_SERVICE:
        raise TypeError("Specify either service or servicio, not both")
    value = service.lower().strip()
    return "".join(
        character for character in unicodedata.normalize("NFD", value)
        if unicodedata.category(character) != "Mn"
    )


@tool
def solicitar_inventario(consulta: str) -> dict:
    """Deriva a Almacén una consulta comercial de disponibilidad, sin inventar repuestos."""
    return {"accion": "CONSULTAR_DISPONIBILIDAD", "consulta": consulta}


@tool
def consultar_armados_pc(intended_use: str, budget_max: str = "") -> list[dict[str, object]]:
    """Propone perfiles de armado con stock y precios actuales del catálogo."""
    from decimal import Decimal, InvalidOperation

    budget = None
    if budget_max.strip():
        try:
            budget = Decimal(budget_max.strip())
        except InvalidOperation as exc:
            raise ValueError("El presupuesto debe ser un importe numérico.") from exc
    settings = load_settings()
    return available_pc_builds(
        ServiceRepository(), intended_use=intended_use, budget_max=budget,
        labor_cost=settings.labor_price_for("pc_build"),
    )


@tool
def modificar_armado_pc(
    profile_id: str,
    intended_use: str,
    category: str,
    replacement_code: str,
    budget_max: str = "",
) -> dict[str, object]:
    """Reemplaza un componente por código exacto y recalcula datos vigentes."""
    from decimal import Decimal, InvalidOperation

    budget = None
    if budget_max.strip():
        try:
            budget = Decimal(budget_max.strip())
        except InvalidOperation as exc:
            raise ValueError("El presupuesto debe ser un importe numérico.") from exc
    settings = load_settings()
    return modify_pc_build(
        ServiceRepository(), profile_id=profile_id, intended_use=intended_use,
        labor_cost=settings.labor_price_for("pc_build"), category=category,
        replacement_code=replacement_code, budget_max=budget,
    )


@tool
def generar_cotizacion(
    parts: list[QuotePartInput],
    state: Annotated[AgentState, InjectedState()],
) -> dict[str, object]:
    """Calcula importes con catálogo/precios compartidos y contexto autenticado."""
    customer_id = state.get("customer_id")
    conversation_id = state.get("conversation_id", "")
    task_type = state.get("quote_task_type")
    quote_types = {
        "maintenance": "REPAIR",
        "diagnosis": "REPAIR",
        "sale": "DIRECT_SALE",
        "pc_build": "PC_BUILD",
    }
    quote_type = quote_types.get(task_type)
    if quote_type is None or state.get("quote_type") != quote_type:
        raise ValueError("El flujo no tiene un tipo de cotización validado.")
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("La conversación autenticada es obligatoria.")
    context = CustomerContext(
        customer_id=customer_id,
        conversation_id=conversation_id,
        pattern_id="decentralized",
    )
    settings = load_settings()
    calculator = make_quote_calculation_tool(
        catalog_service,
        customer_context=context,
        labor_task_type=task_type,
        labor_cost=settings.labor_price_for(task_type),
        quote_type=quote_type,
    )
    return calculator.invoke({"parts": [part.model_dump() for part in parts]})


@tool
def identify_quote_service(service: str) -> str:
    """Identifica un servicio; no inventa tarifa ni confirma una cotización."""
    normalized = normalize_service(service)
    known = ("diagnostico", "mantenimiento", "reparacion", "instalacion")
    if any(item in normalized for item in known):
        return (f"Servicio: {normalized}. Tarifa de mano de obra pendiente de validacion. "
                "No se puede confirmar un precio total.")
    return "No se encontro una cotizacion para el servicio solicitado. Se requiere evaluacion comercial."


normalizar_servicio = normalize_service


@tool
def transferir_a_tecnico(motivo: str) -> str:
    """
    Transfiere una solicitud al agente Tecnico cuando
    requiere diagnostico especializado.
    """

    return f"TRANSFERIR_TECNICO: {motivo}"
