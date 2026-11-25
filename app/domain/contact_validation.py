"""Normalización y validación compartida de datos de contacto."""
import re


_EMAIL = re.compile(
    r"^[A-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,63}|XN--[A-Z0-9-]{2,59})$",
    re.IGNORECASE,
)
_LOCAL_PHONE_CHARS = re.compile(r"^\+?[0-9().\s-]+$")


def normalize_email(value: str | None) -> str | None:
    """Accept common provider addresses, normalize case, and allow an empty optional value."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Ingresa un correo válido, por ejemplo nombre@gmail.com.")
    candidate = value.strip()
    if not candidate:
        return None
    local, separator, domain = candidate.rpartition("@")
    normalized = f"{local}@{domain.casefold()}" if separator else candidate
    if (
        not separator
        or len(normalized) > 254
        or len(local) > 64
        or not _EMAIL.fullmatch(normalized)
        or ".." in local
        or len(domain) > 253
    ):
        raise ValueError("Ingresa un correo válido, por ejemplo nombre@gmail.com.")
    return normalized


def normalize_peru_mobile(value: str) -> str:
    """Store a Peruvian mobile as 9 local digits; accept separators and optional +51."""
    if not isinstance(value, str):
        raise ValueError("Ingresa un celular peruano de 9 dígitos, por ejemplo 987654321.")
    normalized = value.strip()
    if not normalized or not _LOCAL_PHONE_CHARS.fullmatch(normalized):
        raise ValueError("Ingresa un celular peruano de 9 dígitos, por ejemplo 987654321.")
    digits = re.sub(r"\D", "", normalized)
    if len(digits) == 11 and digits.startswith("51"):
        digits = digits[2:]
    if len(digits) != 9:
        raise ValueError("Ingresa un celular peruano de 9 dígitos, por ejemplo 987654321.")
    return digits


def normalize_supplier_phone(value: str | None) -> str | None:
    """Keep supplier contacts international-friendly while rejecting letters and malformed text."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("El teléfono del proveedor debe ser texto con entre 7 y 15 dígitos.")
    normalized = value.strip()
    if not normalized:
        return None
    if not _LOCAL_PHONE_CHARS.fullmatch(normalized):
        raise ValueError("El teléfono del proveedor solo puede contener dígitos, espacios y + ( ) -.")
    digits = re.sub(r"\D", "", normalized)
    if not 7 <= len(digits) <= 15:
        raise ValueError("El teléfono del proveedor debe contener entre 7 y 15 dígitos.")
    return f"+{digits}" if normalized.startswith("+") else digits
