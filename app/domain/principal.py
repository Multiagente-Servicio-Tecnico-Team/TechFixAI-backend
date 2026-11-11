"""Identidad de confianza que entra desde la sesión autenticada."""
from dataclasses import dataclass
from typing import Literal


Role = Literal["CUSTOMER", "ADMIN", "TECHNICIAN"]


@dataclass(frozen=True)
class Principal:
    actor_id: int
    role: Role
    commercial_customer_id: int | None = None

    @classmethod
    def from_session(cls, session_user) -> "Principal":
        role = str(session_user.role)
        if role not in {"CUSTOMER", "ADMIN", "TECHNICIAN"}:
            raise ValueError("El rol de la sesión no es compatible.")
        return cls(
            actor_id=int(session_user.id),
            role=role,
            commercial_customer_id=getattr(session_user, "commercial_customer_id", None),
        )
