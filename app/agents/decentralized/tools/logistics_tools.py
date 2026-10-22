"""Logistics handoffs only. No personal-data or SQL arguments exposed to models."""
from langchain_core.tools import tool
from app.agents.decentralized.tools.software_tools import transferir_a_soporte as _support


@tool
def transferir_a_logistica(motivo: str) -> str:
    """Solicita coordinación; Logística revalida ticket y precondiciones persistidas."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return f"TRANSFERIR_LOGISTICA: {motivo.strip()}"


@tool
def transferir_a_soporte(motivo: str) -> str:
    """Devuelve atención informativa sin confirmar recepción, despacho o garantía."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return _support.invoke({"motivo": motivo.strip()})
