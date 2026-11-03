"""Reglas de negocio incumplidas en una conversación; la API las traduce a códigos HTTP."""


class DomainError(Exception):
    """Base de los errores de negocio. Lleva un código estable para el contrato JSON."""

    code = "domain_error"
    detail = "No se pudo completar la operación."


class ConversationNotFound(DomainError):
    code = "not_found"
    detail = "Conversación no encontrada."


class PatternLocked(DomainError):
    code = "pattern_locked"
    detail = "Para cambiar de patrón, inicia una conversación nueva."


class AmbiguousCatalogMatch(DomainError):
    code = "catalog_ambiguous"
    detail = "Hay varias coincidencias; selecciona el artículo exacto."


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    detail = "No hay existencias suficientes para esa cantidad."


class StaleQuote(DomainError):
    code = "stale_quote"
    detail = "El precio o la disponibilidad cambió; solicita una cotización actualizada."


class OwnershipViolation(DomainError):
    code = "ownership_violation"
    detail = "No se encontró un registro que puedas consultar."


class KnowledgeUnavailable(DomainError):
    code = "knowledge_unavailable"
    detail = "No se encontró evidencia suficiente en las fuentes disponibles."


class NoPendingQuote(DomainError):
    code = "no_quote"
    detail = "No hay un presupuesto pendiente en esta conversación."
