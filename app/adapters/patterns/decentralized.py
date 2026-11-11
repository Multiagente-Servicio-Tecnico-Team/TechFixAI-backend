"""Adaptador del patrón Red descentralizada (`app/agents/decentralized/network.py`).

Comparte agentes de trabajo y estado de negocio con el Jerárquico; por eso el
estado inicial y la traducción de la respuesta son los mismos. Solo cambia el
grafo: pares que se transfieren el trabajo entre sí, sin supervisor.
"""
from typing import Any

from app.adapters.patterns.hierarchical import HierarchicalPattern


class DecentralizedPattern(HierarchicalPattern):
    id = "decentralized"
    name = "Red descentralizada"

    def build_graph(self) -> Any:
        from app.agents.decentralized.network import build_graph

        settings = self._settings_factory()
        settings.require_chat_configuration()
        return build_graph(settings=settings)
