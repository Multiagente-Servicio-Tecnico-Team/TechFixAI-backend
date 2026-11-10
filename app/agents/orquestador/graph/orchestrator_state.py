"""Estado del patrón Orquestador.

Reutiliza el estado de negocio del Jerárquico (los agentes de trabajo son los
mismos) y agrega solo los campos de coordinación del supervisor único.
"""
from app.agents.jerarquico.graph.state import ServiceState


class OrchestratorState(ServiceState, total=False):
    # Último agente que devolvió el control al supervisor en este turno.
    last_agent: str
    # Número de mensajes del cliente ya clasificados; detecta un turno nuevo.
    orchestrator_turn: int
