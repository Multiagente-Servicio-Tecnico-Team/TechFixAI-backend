"""Use cases for customer records and session-to-customer resolution."""
from __future__ import annotations

from typing import Any

from app.domain.customer_commerce import CustomerOrigin
from app.domain.customer_profiles import validate_customer_profile


class CustomerNotFound(Exception):
    pass


class CustomerConflict(Exception):
    pass


class CustomerProfileService:
    def __init__(self, repository):
        self.repository = repository

    def list_customers(self, **filters):
        return self.repository.list_customers(**filters)

    def get_customer(self, customer_id: int):
        return self.repository.get_customer(customer_id)

    def create_manual(self, *, values: dict[str, object], actor_id: int):
        draft = validate_customer_profile(values, origin=CustomerOrigin.MANUAL.value)
        return self.repository.create_customer(draft=draft, actor_id=actor_id)

    def update_customer(self, *, customer_id: int, values: dict[str, object], actor_id: int):
        current = self.repository.get_customer(customer_id)
        if current is None:
            raise CustomerNotFound()
        merged = {"display_name": current["display_name"], "phone": current["phone"], "email": current.get("email")}
        merged.update(values)
        draft = validate_customer_profile(merged, origin=current["origin"], user_id=current.get("user_id"))
        result = self.repository.update_customer(customer_id=customer_id, draft=draft, actor_id=actor_id)
        if result is None:
            raise CustomerNotFound()
        return result

    def link_account(self, *, customer_id: int, user_id: int, actor_id: int, identity_verified: bool):
        if identity_verified is not True:
            raise ValueError("La identidad del cliente debe verificarse antes de vincular la cuenta.")
        result = self.repository.link_customer_account(
            customer_id=customer_id, user_id=user_id, actor_id=actor_id
        )
        if result is None:
            raise CustomerNotFound()
        return result

    def resolve_session_customer(self, authenticated_user: Any):
        """Resolve only from the verified session user; request body is never consulted."""
        if authenticated_user.role != "CUSTOMER":
            raise PermissionError("Esta operación requiere una cuenta CUSTOMER.")
        profile = self.repository.find_by_user_id(authenticated_user.id)
        if profile is not None:
            return profile
        display_name = " ".join(
            part for part in (authenticated_user.first_name, authenticated_user.last_name) if part
        ).strip()
        return self.repository.create_portal_profile(
            user_id=authenticated_user.id,
            display_name=display_name,
            phone=authenticated_user.phone,
            email=authenticated_user.email,
        )
