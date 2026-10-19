from langchain_core.tools import StructuredTool, tool
from langgraph.prebuilt import ToolRuntime


def authenticated_ticket_tool(repository):
    """Bind a server repository; identity is injected, never a model argument."""
    @tool("consultar_estado_ticket")
    def lookup(numero_ticket: int, runtime: ToolRuntime[dict]) -> dict:
        """Consulta un ticket existente autorizado por la sesión autenticada."""
        customer = (runtime.context or {}).get("authenticated_customer_id")
        if type(customer) is not int or customer <= 0:
            return {"verified": False, "detail": "Se requiere una sesión autenticada."}
        try:
            row = repository.get_ticket(customer_id=customer, ticket_id=numero_ticket)
            return {"verified": True, "ticket_id": row["id"], "ticket_code": row["code"], "status": row["status"]}
        except LookupError:
            return {"verified": False, "detail": "No se encontró un ticket autorizado."}
        except Exception:
            return {"verified": False, "detail": "No fue posible verificar el ticket en el almacenamiento."}
    return lookup


def authenticated_ticket_status_tool(repository):
    legacy = authenticated_ticket_tool(repository)

    @tool("get_ticket_status", description=legacy.description)
    def lookup(ticket_id: int, runtime: ToolRuntime[dict]) -> dict:
        return legacy.func(numero_ticket=ticket_id, runtime=runtime)

    return lookup


@tool
def transferir_a_software(motivo: str) -> str:
    """Deriva una consulta lógica a Software sin ejecutar cambios ni diagnosticar."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo de transferencia obligatorio")
    return f"TRANSFERIR_SOFTWARE: {motivo.strip()}"


@tool
def transferir_a_soporte(motivo: str) -> str:
    """Devuelve a Soporte una consulta de ticket o atención general.

    No registra citas ni solicitudes: solamente transfiere la conversación.
    """
    return f"TRANSFERIR_SOPORTE: {motivo}"


@tool #decorador de python
def consultar_estado_ticket(numero_ticket: int) -> str:
    """
    Consulta el estado de un ticket de soporte utilizando su número.
    """
    
    # Datos simulados temporalmente
    tickets = {
        1001: "En revisión",
        1002: "Derivado al área técnica",
        1003: "Resuelto"
    }

    status = tickets.get(numero_ticket)

    if status:
        return f"El ticket {numero_ticket} se encuentra: {status}"

    return f"No se encontró el ticket {numero_ticket}"

def _get_ticket_status(ticket_id: int) -> str:
    return consultar_estado_ticket.func(numero_ticket=ticket_id)


get_ticket_status = StructuredTool.from_function(
    func=_get_ticket_status,
    name="get_ticket_status",
    description=consultar_estado_ticket.description,
)


@tool
def transferir_a_tecnico(motivo: str) -> str:
    """
    Transfiere una solicitud al agente Técnico cuando el problema
    requiere diagnóstico o conocimientos técnicos especializados.
    """
    return f"TRANSFERIR_TECNICO: {motivo}"

@tool
def transferir_a_ventas(motivo: str) -> str:
    """
    Transfiere una solicitud al agente de Ventas cuando el usuario
    requiere información comercial, precios o cotizaciones.
    """
    return f"TRANSFERIR_VENTAS: {motivo}"
