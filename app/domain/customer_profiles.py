"""Commercial customer profile validation, independent of authentication storage."""
from dataclasses import dataclass
from typing import Mapping

from app.domain.customer_commerce import CustomerOrigin


@dataclass(frozen=True)
class CustomerProfileDraft:
    display_name: str
    phone: str
    email: str | None
    origin: CustomerOrigin
    user_id: int | None = None


def validate_customer_profile(
    values: Mapping[str, object], *, origin: str, user_id: int | None = None
) -> CustomerProfileDraft:
    try:
        normalized_origin = CustomerOrigin(origin)
    except ValueError as exc:
        raise ValueError("El origen debe ser MANUAL o PORTAL.") from exc

    name_value = values.get("display_name")
    display_name = name_value.strip() if isinstance(name_value, str) else ""
    if not 2 <= len(display_name) <= 200:
        raise ValueError("El nombre debe tener entre 2 y 200 caracteres.")

    phone_value = values.get("phone")
    phone = phone_value.strip() if isinstance(phone_value, str) else ""
    if not 7 <= len(phone) <= 30:
        raise ValueError("El teléfono debe tener entre 7 y 30 caracteres.")

    email_value = values.get("email")
    email: str | None = None
    if email_value is not None:
        if not isinstance(email_value, str):
            raise ValueError("El correo debe ser texto o null.")
        email = email_value.strip().casefold()
        if len(email) > 255 or not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("El correo no es válido.")

    if user_id is not None and (isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0):
        raise ValueError("La cuenta vinculada no es válida.")
    if normalized_origin is CustomerOrigin.PORTAL and user_id is None:
        raise ValueError("Un perfil PORTAL requiere una cuenta autenticada.")
    return CustomerProfileDraft(display_name, phone, email, normalized_origin, user_id)
