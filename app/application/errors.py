"""Fallos de servicio que los adaptadores traducen desde sus excepciones técnicas.

Los mensajes son los que ve el cliente; nunca incluyen el texto de la excepción original.
"""
from typing import Literal


class ApplicationError(Exception):
    detail = "No se pudo completar la operación."


class RateLimited(ApplicationError):
    detail = "Enviaste muchos mensajes seguidos. Espera un minuto."


class StorageUnavailable(ApplicationError):
    """La base de datos o el almacenamiento no respondieron durante la operación."""

    detail = "El asistente no pudo completar la operación."

    def __init__(self, detail: str | None = None):
        super().__init__(detail or self.detail)
        if detail:
            self.detail = detail


class PatternFailure(ApplicationError):
    """El proveedor LLM o el propio patrón no produjeron una respuesta válida."""

    DETAILS = {
        "llm": "El proveedor LLM no pudo procesar el mensaje.",
        "pattern": "El patrón no pudo completar el mensaje.",
    }

    def __init__(self, kind: Literal["llm", "pattern"]):
        self.kind = kind
        self.detail = self.DETAILS[kind]
        super().__init__(self.detail)
