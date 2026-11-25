"""Estado de la Red descentralizada.

Reutiliza el estado de negocio del Jerárquico (los agentes de trabajo son los
mismos) y agrega solo los campos de coordinación entre pares.
"""
from typing import Any

from app.agents.jerarquico.graph.state import ServiceState


class NetworkState(ServiceState, total=False):
    # Par que atendió el último paso del turno.
    active_peer: str
    # Transferencias validadas del turno actual: origen, destino y motivo.
    handoffs: list[dict[str, Any]]
