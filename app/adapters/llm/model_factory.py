"""Modelo compartido para que las comparaciones cambien solo la topología."""
from dataclasses import dataclass
from typing import Any

from app.settings import Settings, load_settings


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    temperature: float = 0.0

    @property
    def identifier(self) -> str:
        return f"{self.provider}:{self.model}:temperature={self.temperature:g}"


def model_profile(settings: Settings | None = None) -> ModelProfile:
    settings = settings or load_settings()
    if not settings.groq_model:
        raise RuntimeError("GROQ_MODEL no está configurado.")
    return ModelProfile(provider="groq", model=settings.groq_model)


def create_model(settings: Settings | None = None) -> Any:
    settings = settings or load_settings()
    settings.require_chat_configuration()
    from langchain_groq import ChatGroq

    profile = model_profile(settings)
    return ChatGroq(
        model=profile.model,
        api_key=settings.groq_api_key,
        temperature=profile.temperature,
    )
