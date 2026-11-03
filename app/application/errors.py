"""Fallos de servicio que los adaptadores traducen desde sus excepciones técnicas.

Los mensajes son los que ve el cliente; nunca incluyen el texto de la excepción original.
"""
from typing import Literal


class ApplicationError(Exception):
    code = "application_error"
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


class CapabilityFailure(ApplicationError):
    """Resultado seguro y estable para un rechazo de una capacidad compartida."""


class AmbiguousCatalogFailure(CapabilityFailure):
    code = "catalog_ambiguous"
    detail = "Hay varias coincidencias; selecciona el artículo exacto."


class InsufficientStockFailure(CapabilityFailure):
    code = "insufficient_stock"
    detail = "No hay existencias suficientes para esa cantidad."


class StaleQuoteFailure(CapabilityFailure):
    code = "stale_quote"
    detail = "El precio o la disponibilidad cambió; solicita una cotización actualizada."


class OwnershipFailure(CapabilityFailure):
    code = "ownership_violation"
    detail = "No se encontró un registro que puedas consultar."


class RefundEligibilityFailure(CapabilityFailure):
    code = "refund_ineligible"
    detail = "El pago no cumple los requisitos para registrar una solicitud de reembolso."


class KnowledgeUnavailableFailure(CapabilityFailure):
    code = "knowledge_unavailable"
    detail = "No se encontró evidencia suficiente en las fuentes disponibles."


class AudioRequestError(ApplicationError):
    status_code = 422
    code = "audio_invalid"
    detail = "No se pudo procesar el audio. Revisa la grabación e inténtalo de nuevo."


class AudioTooLarge(AudioRequestError):
    status_code = 413
    code = "audio_too_large"
    detail = "El audio supera el tamaño máximo permitido."


class UnsupportedAudioType(AudioRequestError):
    status_code = 415
    code = "unsupported_audio_type"
    detail = "El formato de audio no está admitido."


class AudioUnavailable(ApplicationError):
    status_code = 503
    code = "audio_unavailable"
    detail = "La transcripción de audio no está disponible. Puedes continuar por escrito."


class AudioTranscriptionTimeout(ApplicationError):
    status_code = 504
    code = "audio_timeout"
    detail = "La transcripción tardó demasiado. Inténtalo de nuevo."


class AudioQuotaExceeded(ApplicationError):
    status_code = 429
    code = "audio_rate_limited"
    detail = "Alcanzaste el límite de envíos de audio. Espera un minuto e inténtalo de nuevo."


class AudioIdempotencyConflict(ApplicationError):
    status_code = 409
    code = "audio_request_conflict"
    detail = "El identificador de solicitud ya se usó con otros datos."


class AccountingError(ApplicationError):
    """Error contable con respuesta estable, sin detalles de SQL."""

    status_code = 422
    code = "accounting_validation"
    detail = "Los datos del asiento no son válidos."


class AccountingConflict(AccountingError):
    status_code = 409
    code = "accounting_conflict"
    detail = "El asiento entra en conflicto con un registro existente."


class AccountingNotFound(AccountingError):
    status_code = 404
    code = "accounting_not_found"
    detail = "No se encontró el asiento solicitado."


class AccountingStorageUnavailable(AccountingError):
    status_code = 503
    code = "accounting_storage_unavailable"
    detail = "El servicio contable no está disponible. Inténtalo más tarde."

    def __init__(self):
        super().__init__(self.detail)


class ConversationActionError(ApplicationError):
    """Safe conversation/recovery error shared by text and audio adapters."""
    def __init__(self, status_code: int, detail: str, code: str = "conversation_conflict"):
        self.status_code, self.detail, self.code = status_code, detail, code
        super().__init__(detail)
