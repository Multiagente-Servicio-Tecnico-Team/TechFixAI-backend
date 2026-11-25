"""Adaptador del patrón Orquestador / supervisor (`app/agents/orquestador`).

Comparte agentes de trabajo y estado de negocio con el Jerárquico; por eso el
estado inicial y la traducción de la respuesta son los mismos. Solo cambia el
grafo (topología en estrella con un supervisor único).
"""
from typing import Any

from app.adapters.patterns.hierarchical import HierarchicalPattern


class OrchestratorPattern(HierarchicalPattern):
    id = "orchestrator"
    name = "Orquestador / supervisor"

    def build_graph(self) -> Any:
        from app.agents.orquestador import build_graph

        settings = self._settings_factory()
        settings.require_chat_configuration()
        return build_graph(settings=settings)
