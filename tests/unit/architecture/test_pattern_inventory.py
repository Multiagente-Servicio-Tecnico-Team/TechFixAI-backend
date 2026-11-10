from importlib import import_module

from app.adapters.patterns.registry import PATTERN_CLASSES
from app.rag.retriever import RetrievedPassage, retrieve_documents
from app.rag.sources import knowledge_sources


def test_all_three_distinct_pattern_graphs_remain_registered():
    assert {pattern.id for pattern in PATTERN_CLASSES} == {
        "hierarchical", "orchestrator", "decentralized"
    }
    modules = {
        "hierarchical": "app.agents.jerarquico.graph.builder",
        "orchestrator": "app.agents.orquestador.graph.hub",
        "decentralized": "app.agents.decentralized.network",
    }
    for pattern in PATTERN_CLASSES:
        assert import_module(modules[pattern.id])


def test_pattern_knowledge_entrypoints_reach_shared_retriever_and_manifest():
    assert callable(retrieve_documents)
    assert RetrievedPassage.__dataclass_fields__
    assert knowledge_sources()
    assert import_module("app.agents.jerarquico.knowledge_retrieval")
    assert import_module("app.rag.tools")
