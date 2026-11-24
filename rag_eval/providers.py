"""Clientes de evaluación: JSON Schema estricto, caché local y errores redactados."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, OpenAI, pydantic_function_tool
from ragas.llms.base import InstructorBaseRagasLLM

ENDPOINT = "https://api.groq.com/openai/v1"


def cache_key(payload):
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def daily_quota(error):
    if getattr(error, "status_code", None) != 429:
        return None
    body = getattr(error, "body", {})
    detail = body.get("error", body) if isinstance(body, dict) else {}
    message = detail.get("message", "").lower() if isinstance(detail, dict) else ""
    if "tokens per day" in message:
        return "daily_tokens"
    if "requests per day" in message:
        return "daily_requests"
    return None

def safe_error(error):
    body = getattr(error, "body", None)
    detail = body.get("error", body) if isinstance(body, dict) else {}
    code = detail.get("code") if isinstance(detail, dict) else None
    # Solo códigos cortos de máquina: nunca texto de excepciones ni contenido.
    if not isinstance(code, str) or not code.replace("_", "").isalnum() or len(code) > 60:
        code = None
    return {"error_type": type(error).__name__, "http_status": getattr(error, "status_code", None), "code": code, "quota": daily_quota(error)}


def retry_delay(error, attempt):
    if daily_quota(error):
        return None
    if isinstance(error, APIConnectionError):
        return min(2 ** attempt, 8)
    if isinstance(error, APIStatusError) and (error.status_code == 429 or error.status_code >= 500):
        try:
            delay = float(error.response.headers.get("retry-after", 2 ** attempt))
        except (TypeError, ValueError):
            delay = 2 ** attempt
        return min(max(delay, 1), 45)
    return None


def schema_format(schema):
    # Utiliza el convertidor público del SDK para required/additionalProperties.
    parameters = pydantic_function_tool(schema)["function"]["parameters"]
    return {"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": True, "schema": parameters}}


def validate_verdicts(parsed):
    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"verdict", "attributed"} and child not in (0, 1):
                    raise ValueError("El evaluador devolvió un veredicto no binario")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(parsed.model_dump())
    return parsed

class CompletionStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.calls = 0

    def read(self, payload):
        path = self.directory / (cache_key(payload) + ".json")
        if path.exists():
            self.hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["content"]
        return None

    def write(self, payload, content):
        path = self.directory / (cache_key(payload) + ".json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)


class ProjectModel:
    """Puente de transporte; los prompts y reglas se ejecutan en funciones del proyecto."""
    def __init__(self, api_key, model, store, schema=None):
        self.api_key = api_key
        self.model = model
        self.store = store
        self.schema = schema

    def with_structured_output(self, schema, *, method):
        if method != "json_mode":
            raise ValueError("Método de salida no admitido por el puente de evaluación")
        return ProjectModel(self.api_key, self.model, self.store, schema)

    def invoke(self, messages):
        roles = {"system": "system", "human": "user", "ai": "assistant"}
        payload = {"model": self.model, "temperature": 0, "reasoning_effort": "low", "max_completion_tokens": 4096,
                   "messages": [{"role": roles[m.type], "content": m.content} for m in messages]}
        if self.schema:
            # Respeta el método JSON mode que solicita el componente de producción.
            payload["response_format"] = {"type": "json_object"}
        content = self.store.read(payload)
        if content is None:
            with OpenAI(api_key=self.api_key, base_url=ENDPOINT, timeout=60, max_retries=0) as client:
                for attempt in range(3):
                    try:
                        self.store.calls += 1
                        result = client.chat.completions.create(**payload)
                        if result.choices[0].finish_reason != "stop":
                            raise ValueError("Generación incompleta")
                        content = result.choices[0].message.content
                        if not content:
                            raise ValueError("Respuesta vacía")
                        if self.schema:
                            self.schema.model_validate_json(content)
                        self.store.write(payload, content)
                        break
                    except (APIConnectionError, APIStatusError) as error:
                        delay = retry_delay(error, attempt)
                        if delay is None or attempt == 2:
                            raise
                        time.sleep(delay)
        return self.schema.model_validate_json(content) if self.schema else SimpleNamespace(content=content)


class StrictGroqJudge(InstructorBaseRagasLLM):
    """Implementa el contrato Ragas sin el ciclo de reparación JSON de Instructor."""
    def __init__(self, client, model, store):
        self.client = client
        self.model = model
        self.store = store

    def generate(self, prompt, response_model):
        raise RuntimeError("Usa las métricas asíncronas con este evaluador")

    async def agenerate(self, prompt, response_model):
        payload = {"model": self.model, "temperature": 0, "reasoning_effort": "low", "max_completion_tokens": 4096,
                   "messages": [{"role": "user", "content": prompt}], "response_format": schema_format(response_model)}
        content = self.store.read(payload)
        if content is not None:
            return validate_verdicts(response_model.model_validate_json(content))
        for attempt in range(3):
            try:
                self.store.calls += 1
                result = await self.client.chat.completions.create(**payload)
                if result.choices[0].finish_reason != "stop":
                    raise ValueError("Evaluación incompleta")
                content = result.choices[0].message.content
                parsed = validate_verdicts(response_model.model_validate_json(content or ""))
                self.store.write(payload, content)
                return parsed
            except (APIConnectionError, APIStatusError) as error:
                delay = retry_delay(error, attempt)
                if delay is None or attempt == 2:
                    raise
                await asyncio.sleep(delay)