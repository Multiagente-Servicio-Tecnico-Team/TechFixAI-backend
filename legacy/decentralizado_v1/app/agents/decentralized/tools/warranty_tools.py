"""Handoffs without SQL or model-controlled commercial authorization."""
from langchain_core.tools import tool
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica, transferir_a_soporte


@tool
def transferir_a_garantia(motivo: str) -> str:
    """Consulta o revisión de garantía; el destino verifica propiedad y datos reales."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return "TRANSFERIR_GARANTIA: " + motivo.strip()


garantia_tools = [transferir_a_logistica, transferir_a_soporte]
