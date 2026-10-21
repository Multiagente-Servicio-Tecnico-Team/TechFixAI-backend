"""Registro (fábrica) de los patrones disponibles en el chat."""
from collections.abc import Callable, Mapping

from app.adapters.patterns.base import GraphFactory, GraphPattern, TraceContextFactory
from app.adapters.patterns.decentralized import DecentralizedPattern
from app.adapters.patterns.hierarchical import HierarchicalPattern
from app.adapters.patterns.orchestrator import OrchestratorPattern
from app.settings import Settings, load_settings

PATTERN_CLASSES: tuple[type[GraphPattern], ...] = (HierarchicalPattern, OrchestratorPattern, DecentralizedPattern)
PATTERN_NAMES: dict[str, str] = {cls.id: cls.name for cls in PATTERN_CLASSES}


def build_patterns(
    graph_factories: Mapping[str, GraphFactory] | None = None,
    *,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
) -> dict[str, GraphPattern]:
    """Crea un adaptador por patrón. `graph_factories` reemplaza los grafos (pruebas)."""
    if graph_factories is not None and set(graph_factories) != set(PATTERN_NAMES):
        raise ValueError("Debe configurarse exactamente cada patrón disponible.")
    return {
        cls.id: cls(
            graph_factory=graph_factories[cls.id] if graph_factories else None,
            trace_context_factory=trace_context_factory,
            settings_factory=settings_factory,
        )
        for cls in PATTERN_CLASSES
    }
