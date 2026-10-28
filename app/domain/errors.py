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


class NoPendingQuote(DomainError):
    code = "no_quote"
    detail = "No hay un presupuesto pendiente en esta conversación."
