"""Regresiones de una propuesta aislada; no se aplica al RAG del proyecto."""
import pytest

from rag_eval.retrieval_candidate import prepare_candidate_case, prepare_query, retrieve_candidate_faq


@pytest.fixture(autouse=True)
def isolated_retrieval(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "lexical")


@pytest.mark.parametrize('question,expected', [
    ('¿Podrías ayudarme? Windows enseña INACCESSIBLE_BOOT_DEVICE 0x0000007B; quiero saber qué revisión técnica corresponde.', 'manual_servicio:002'),
    ('Mi ordenador se apaga después de encender; ¿podría indicarme posibles causas?', 'manual_servicio:003'),
    ('El logo de Windows se queda congelado durante el arranque, necesito saber qué revisión requiere.', 'manual_servicio:004'),
])
def test_candidate_recovers_unseen_technical_formulations_without_editing_question(question, expected):
    sample={'route':'technical','mode':'hardware','user_input':question}
    original=dict(sample)
    prepared=prepare_candidate_case(sample)
    assert expected in prepared['source_ids']
    assert sample==original
    assert prepared['state']['messages'][0].content==question
    assert prepared['state']['failure_description']==question


def test_candidate_query_preserves_negation_timing_and_identifiers():
    query=prepare_query('No se apaga después de encender sin cargador; necesito revisión técnica de SSD-1TB-X.')
    assert {'no','despues','encender','sin','cargador','ssd-1tb-x'}.issubset(query.split())
    assert 'revision' not in query


def test_unknown_error_code_does_not_retrieve_a_different_error():
    prepared=prepare_candidate_case({'route':'technical','mode':'software','user_input':'Pantalla azul con el error 0xDEADBEEF, ¿qué revisión necesita?'})
    assert prepared['contexts']==[]


@pytest.mark.parametrize('question,section', [
    ('¿Cuánto dura la garantía de un armado de PC?', 'Garantía'),
    ('¿Cuánto cuesta diagnóstico y armado?', 'Tarifas y cotizaciones'),
    ('¿Qué medios de pago aceptan?', 'Pagos'),
])
def test_candidate_selects_explicit_faq_topic_before_secondary_context(question, section):
    prepared=retrieve_candidate_faq(question,limit=1)
    assert prepared['selected_sections']==[section]


def test_candidate_covers_multiple_faq_topics_within_limit():
    prepared=retrieve_candidate_faq('¿Dónde está la tienda y en qué horario atienden?',limit=2)
    assert set(prepared['selected_sections'])=={'Ubicación de la tienda','Horario de atención'}
    assert len(prepared['contexts'])==2


def test_generic_help_does_not_turn_an_unrelated_question_into_services():
    assert retrieve_candidate_faq('Necesito ayuda con una receta de cocina')['contexts']==[]


def test_candidate_rejects_invalid_limit():
    with pytest.raises(ValueError):
        retrieve_candidate_faq('garantía',limit=0)