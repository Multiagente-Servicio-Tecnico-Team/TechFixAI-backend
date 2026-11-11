"""Verifica que evaluar el backend no cambie sus parámetros de generación."""
import json
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

pytest.importorskip("ragas", exc_type=ImportError)

from app.settings import Settings
from rag_eval.native_provider import NativeProjectModel, create_native_model
from rag_eval.providers import CompletionStore, daily_quota, safe_error
from rag_eval.reporting import save_report


def settings_fixture():
    return Settings(groq_api_key='fixture-key', groq_model='fixture-model', database_url=None,
                    langsmith_api_key=None, langsmith_tracing=False, langsmith_project='tests',
                    langsmith_hide_inputs=True, langsmith_hide_outputs=True,
                    labor_maintenance_price=Decimal('35'), labor_diagnosis_price=Decimal('50'))


def test_native_factory_preserves_generation_defaults_and_caches(tmp_path, monkeypatch):
    wrapper=create_native_model(settings_fixture(),CompletionStore(tmp_path))
    calls=[]
    def fake_create(**kwargs):
        calls.append(kwargs)
        return {'id':'test-completion','model':'fixture-model','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'OK'}}], 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
    monkeypatch.setattr(wrapper.model.client,'create',fake_create)
    first=wrapper.invoke([HumanMessage(content='Consulta sintética')])
    second=wrapper.invoke([HumanMessage(content='Consulta sintética')])
    assert first.content==second.content=='OK'
    assert len(calls)==1
    assert calls[0]['temperature']==wrapper.model.temperature
    assert calls[0]['temperature']==pytest.approx(0,abs=1e-7)
    assert calls[0]['parallel_tool_calls'] is False
    assert calls[0].get('reasoning_effort') is None
    assert calls[0].get('max_completion_tokens') is None
    assert calls[0].get('max_tokens') is None
    assert 'api_key' not in wrapper.profile


def test_native_factory_does_not_change_database_environment(monkeypatch,tmp_path):
    import app.adapters.llm.model_factory as factory
    monkeypatch.setenv('DATABASE_URL','')
    captured=[]
    monkeypatch.setattr(factory,'create_model',lambda settings: captured.append(settings) or object())
    original=settings_fixture()
    create_native_model(original,CompletionStore(tmp_path))
    import os
    assert os.environ['DATABASE_URL']==''
    assert original.database_url is None
    assert captured[0].database_url=='evaluation://unused'
    assert captured[0].groq_model==original.groq_model
    assert captured[0].groq_api_key==original.groq_api_key


def test_native_structured_output_reuses_original_method(tmp_path):
    class Diagnosis(BaseModel):
        text:str
    calls=[]
    class FakeModel:
        def with_structured_output(self,schema,*,method):
            calls.append((schema,method))
            return SimpleNamespace(invoke=lambda messages: Diagnosis(text='Diagnóstico provisional'))
    wrapper=NativeProjectModel(FakeModel(),{'model':'test'},CompletionStore(tmp_path))
    structured=wrapper.with_structured_output(Diagnosis,method='json_mode')
    assert structured.invoke([HumanMessage(content='Síntoma')]).text=='Diagnóstico provisional'
    assert structured.invoke([HumanMessage(content='Síntoma')]).text=='Diagnóstico provisional'
    assert calls==[(Diagnosis,'json_mode')]


def test_groq_daily_quota_is_detected_without_logging_message():
    from groq import RateLimitError
    response=httpx.Response(429,request=httpx.Request('POST','https://example.invalid'))
    error=RateLimitError('PRIVATE ACCOUNT',response=response,body={'error':{'message':'PRIVATE ACCOUNT reached tokens per day','code':'rate_limit_exceeded'}})
    assert daily_quota(error)=='daily_tokens'
    assert 'PRIVATE' not in json.dumps(safe_error(error))


def test_report_identifies_distinct_generator_and_judge(tmp_path):
    save_report(tmp_path,[],{'planned_cases':0,'model':'20b','judge_model':'120b','configured_backend_model':'20b','model_matches_backend':True,'same_model_for_generation_and_judging':False})
    text=(tmp_path/'report.md').read_text(encoding='utf-8')
    assert 'El mismo modelo genera y evalúa.' not in text
    assert '20b' in text and '120b' in text