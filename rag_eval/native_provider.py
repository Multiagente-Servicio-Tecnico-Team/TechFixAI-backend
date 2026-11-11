"""Modelo real del proyecto con caché local; sin cambiar sus parámetros de generación."""
from dataclasses import asdict, replace
import importlib.metadata
import json
from types import SimpleNamespace


class NativeProjectModel:
    def __init__(self, model, profile, store, schema=None, method=None):
        self.model = model
        self.profile = profile
        self.store = store
        self.schema = schema
        self.method = method

    def with_structured_output(self, schema, *, method):
        return NativeProjectModel(self.model, self.profile, self.store, schema, method)

    def invoke(self, messages):
        payload = {
            "transport": "project_model_factory_chatgroq_v1",
            "profile": self.profile,
            "messages": [{"type": message.type, "content": message.content} for message in messages],
            "schema": self.schema.model_json_schema() if self.schema else None,
            "method": self.method,
        }
        cached = self.store.read(payload)
        if cached is not None:
            data = json.loads(cached)["data"]
            return self.schema.model_validate(data) if self.schema else SimpleNamespace(content=data)
        runnable = self.model.with_structured_output(self.schema, method=self.method) if self.schema else self.model
        self.store.calls += 1
        result = runnable.invoke(messages)
        data = result.model_dump(mode="json") if self.schema else result.content
        if not self.schema and not isinstance(data, str):
            raise ValueError("La respuesta del modelo no es textual")
        self.store.write(payload, json.dumps({"data": data}, ensure_ascii=False))
        return result


def native_profile(settings):
    from app.adapters.llm.model_factory import model_profile
    return {**asdict(model_profile(settings)), "factory": "app.adapters.llm.model_factory.create_model",
            "versions": {name: importlib.metadata.version(name) for name in ("langchain-groq", "groq", "langchain-core")}}


def create_native_model(settings, store):
    from app.adapters.llm.model_factory import create_model
    # La fábrica valida una URL de BD aunque solo crea el LLM. El proceso mantiene
    # DATABASE_URL vacío y no usa este marcador para conectar ni crear un engine.
    isolated = replace(settings, database_url="evaluation://unused", langsmith_tracing=False)
    return NativeProjectModel(create_model(isolated), native_profile(settings), store)