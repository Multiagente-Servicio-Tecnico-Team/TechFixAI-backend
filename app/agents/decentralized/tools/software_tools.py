"""Transferencias de Software; no ejecutan agentes ni cambios en dispositivos."""
from typing import Literal

from langchain_core.tools import tool

from app.agents.decentralized.tools.soporte_tools import (
    transferir_a_soporte as _a_soporte,
    transferir_a_tecnico as _a_tecnico,
)
from app.agents.decentralized.tools.tecnico_tools import transferir_a_ventas as _a_ventas


def _require_reason(motivo: str) -> str:
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo de transferencia obligatorio")
    return motivo.strip()


@tool
def transferir_a_soporte(motivo: str) -> str:
    """Deriva a Atención una consulta general o presencial, sin registrar citas."""
    return _a_soporte.invoke({"motivo": _require_reason(motivo)})


@tool
def transferir_a_tecnico(motivo: str) -> str:
    """Deriva a Hardware una sospecha física indicando evidencia e incertidumbre."""
    return _a_tecnico.invoke({"motivo": _require_reason(motivo)})


@tool
def transferir_a_ventas(motivo: str, alcance: Literal["solo_servicio"]) -> dict:
    """Solicita cotizar un servicio definido sin repuestos; no calcula precios.

    Declara solo_servicio explícitamente. Si se requieren componentes o falta
    determinarlo, consulta primero a Hardware mediante transferir_a_tecnico.
    La transferencia no autoriza ni ejecuta el servicio.
    """
    motivo = _require_reason(motivo)
    if alcance != "solo_servicio":
        raise ValueError("Software solo deriva servicios sin repuestos a Ventas")
    return _a_ventas.invoke({"motivo": motivo, "alcance": alcance})
