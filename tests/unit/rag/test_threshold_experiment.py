"""Umbral inclusivo, alcance técnico e invariantes del experimento."""
import math

from langchain_core.documents import Document
import pytest

from app.rag.retriever import retrieve_documents


def boundary_document():
    return Document(page_content="alpha bravo charlie", metadata={"source_id":"boundary"})


def test_threshold_accepts_exact_float_boundary(monkeypatch):
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "lexical")
    query="alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    assert retrieve_documents(query,documents=[boundary_document()]) == []
    result=retrieve_documents(query,documents=[boundary_document()],lexical_min_coverage=0.30)
    assert len(result)==1 and result[0].score==3/10
    assert retrieve_documents(query,documents=[boundary_document()],lexical_min_coverage=math.nextafter(0.30,1.0))==[]


@pytest.mark.parametrize("value", [float("nan"),float("inf"),-0.1,1.01,True,"0.30",None])
def test_threshold_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        retrieve_documents("alpha",documents=[boundary_document()],lexical_min_coverage=value)


def test_experiment_overrides_only_technical_binding_and_restores():
    from app.agents.jerarquico import retriever as technical
    from app.rag import faq, retriever as shared
    from rag_eval.threshold_experiment import technical_threshold
    original=technical.retrieve_documents
    shared_original=shared.retrieve_documents
    faq_original=faq.retrieve_documents
    with pytest.raises(RuntimeError):
        with technical_threshold(0.30):
            assert technical.retrieve_documents is not original
            assert shared.retrieve_documents is shared_original
            assert faq.retrieve_documents is faq_original
            raise RuntimeError("salida de prueba")
    assert technical.retrieve_documents is original
    assert shared.retrieve_documents is shared_original


def test_lower_threshold_does_not_create_context_for_technical_control(monkeypatch):
    from rag_eval.runtime import prepare_case
    from rag_eval.threshold_experiment import technical_threshold
    monkeypatch.setenv("RAG_RETRIEVAL_MODE","lexical")
    sample={"route":"technical","user_input":"¿Cómo preparo una receta de pan con harina y levadura?"}
    for value in (0.34,0.33,0.30,0.29):
        with technical_threshold(value):
            assert prepare_case(sample)["contexts"]==[]
