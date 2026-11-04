"""PostgreSQL adapter for commercial customer profiles."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.application.customer_profiles import CustomerConflict
from app.database.connection import SessionLocal, get_engine


def _as_customer(row) -> dict[str, object]:
    result = dict(row)
    result["account_linked"] = result.get("user_id") is not None
    return result


class CustomerRepositoryAdapter:
    def __init__(self, session_factory=None):
        if session_factory is None:
            get_engine()
            session_factory = SessionLocal
        self._session_factory = session_factory

    def list_customers(self, *, search: str | None = None, origin: str | None = None, limit: int = 50, offset: int = 0):
        predicates = ["(CAST(:origin AS text) IS NULL OR c.origin = CAST(:origin AS text))"]
        params: dict[str, object] = {"origin": origin, "limit": limit, "offset": offset}
        if search:
            predicates.append("(c.display_name ILIKE :search OR c.phone ILIKE :search OR c.email ILIKE :search)")
            params["search"] = f"%{search.strip()}%"
        where = " AND ".join(predicates)
        query = text(f"""SELECT c.id, c.display_name, c.phone, c.email, c.origin, c.user_id,
                           c.active, c.created_by_user_id, c.created_at, c.updated_at
                    FROM public.customers c WHERE {where}
                    ORDER BY c.display_name, c.id LIMIT :limit OFFSET :offset""")
        count = text(f"SELECT count(*) FROM public.customers c WHERE {where}")
        with self._session_factory() as session:
            rows = session.execute(query, params).mappings().all()
            total = session.execute(count, params).scalar_one()
        return {"items": [_as_customer(row) for row in rows], "total": int(total)}

    def get_customer(self, customer_id: int):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT id, display_name, phone, email, origin, user_id,
                    active, created_by_user_id, created_at, updated_at
                    FROM public.customers WHERE id=:id"""), {"id": customer_id}).mappings().first()
        return _as_customer(row) if row else None

    def find_by_user_id(self, user_id: int):
        with self._session_factory() as session:
            row = session.execute(text("""SELECT id, display_name, phone, email, origin, user_id,
                    active, created_by_user_id, created_at, updated_at
                    FROM public.customers WHERE user_id=:user_id"""), {"user_id": user_id}).mappings().first()
        return _as_customer(row) if row else None

    def create_customer(self, *, draft, actor_id: int):
        try:
            with self._session_factory() as session, session.begin():
                row = session.execute(text("""INSERT INTO public.customers
                    (display_name, phone, email, origin, user_id, created_by_user_id)
                    VALUES (:name, :phone, :email, :origin, :user_id, :actor)
                    RETURNING id, display_name, phone, email, origin, user_id, active,
                              created_by_user_id, created_at, updated_at"""),
                    {"name": draft.display_name, "phone": draft.phone, "email": draft.email,
                     "origin": draft.origin.value, "user_id": draft.user_id, "actor": actor_id},
                ).mappings().one()
                session.execute(text("""INSERT INTO public.customer_audit_events
                    (customer_id, actor_user_id, event_type, changed_fields)
                    VALUES (:customer, :actor, 'CREATED', jsonb_build_object('origin', 'MANUAL'))"""),
                    {"customer": row["id"], "actor": actor_id})
            return _as_customer(row)
        except IntegrityError as exc:
            raise CustomerConflict("El cliente entra en conflicto con una relación existente.") from exc
        except SQLAlchemyError:
            raise

    def create_portal_profile(self, *, user_id: int, display_name: str, phone: str, email: str | None):
        try:
            with self._session_factory() as session, session.begin():
                user = session.execute(text("""SELECT id, name, last_name, phone, email, active, role::text AS role
                    FROM public.users WHERE id=:id FOR UPDATE"""), {"id": user_id}).mappings().first()
                if not user or not user["active"] or user["role"] != "CUSTOMER":
                    raise CustomerConflict("La sesión no corresponde a una cuenta CUSTOMER activa.")
                linked = session.execute(text("SELECT id FROM public.customers WHERE user_id=:id"), {"id": user_id}).scalar_one_or_none()
                if linked:
                    row = session.execute(text("""SELECT id, display_name, phone, email, origin, user_id,
                        active, created_by_user_id, created_at, updated_at FROM public.customers WHERE id=:id"""),
                        {"id": linked}).mappings().one()
                    return _as_customer(row)
                row = session.execute(text("""INSERT INTO public.customers
                    (display_name, phone, email, origin, user_id)
                    VALUES (:name, :phone, :email, 'PORTAL', :user_id)
                    RETURNING id, display_name, phone, email, origin, user_id, active,
                              created_by_user_id, created_at, updated_at"""),
                    {"name": display_name, "phone": phone, "email": email, "user_id": user_id},
                ).mappings().one()
            return _as_customer(row)
        except IntegrityError as exc:
            raise CustomerConflict("La cuenta ya quedó vinculada a otro perfil comercial.") from exc

    def update_customer(self, *, customer_id: int, draft, actor_id: int):
        with self._session_factory() as session, session.begin():
            previous = session.execute(text("""SELECT display_name, phone, email FROM public.customers
                WHERE id=:id FOR UPDATE"""), {"id": customer_id}).mappings().first()
            if previous is None:
                return None
            changed = {
                key: getattr(draft, key)
                for key in ("display_name", "phone", "email")
                if previous[key] != getattr(draft, key)
            }
            row = session.execute(text("""UPDATE public.customers SET display_name=:name,
                phone=:phone, email=:email, updated_at=CURRENT_TIMESTAMP
                WHERE id=:id RETURNING id, display_name, phone, email, origin, user_id,
                active, created_by_user_id, created_at, updated_at"""),
                {"name": draft.display_name, "phone": draft.phone, "email": draft.email, "id": customer_id},
            ).mappings().first()
            if changed:
                import json
                session.execute(text("""INSERT INTO public.customer_audit_events
                    (customer_id, actor_user_id, event_type, changed_fields)
                    VALUES (:customer, :actor, 'UPDATED', CAST(:fields AS jsonb))"""),
                    {"customer": customer_id, "actor": actor_id, "fields": json.dumps(changed)})
        return _as_customer(row) if row else None

    def link_customer_account(self, *, customer_id: int, user_id: int, actor_id: int):
        try:
            with self._session_factory() as session, session.begin():
                customer = session.execute(text("SELECT id, user_id FROM public.customers WHERE id=:id FOR UPDATE"), {"id": customer_id}).mappings().first()
                if not customer:
                    return None
                user = session.execute(text("SELECT id, active, role::text AS role FROM public.users WHERE id=:id FOR UPDATE"), {"id": user_id}).mappings().first()
                if not user or not user["active"] or user["role"] != "CUSTOMER":
                    raise CustomerConflict("La cuenta debe existir, estar activa y tener rol CUSTOMER.")
                existing = session.execute(text("SELECT id FROM public.customers WHERE user_id=:id FOR UPDATE"), {"id": user_id}).scalar_one_or_none()
                if existing is not None and int(existing) != customer_id:
                    raise CustomerConflict("La cuenta ya está vinculada a otro perfil.")
                session.execute(text("""UPDATE public.customers SET user_id=:user_id,
                    updated_at=CURRENT_TIMESTAMP WHERE id=:id"""), {"user_id": user_id, "id": customer_id})
                session.execute(text("""INSERT INTO public.customer_audit_events
                    (customer_id, actor_user_id, event_type, changed_fields)
                    VALUES (:customer, :actor, 'ACCOUNT_LINKED', jsonb_build_object('user_id', :user))"""),
                    {"customer": customer_id, "actor": actor_id, "user": user_id})
                row = session.execute(text("""SELECT id, display_name, phone, email, origin, user_id,
                    active, created_by_user_id, created_at, updated_at FROM public.customers WHERE id=:id"""),
                    {"id": customer_id}).mappings().one()
            return _as_customer(row)
        except IntegrityError as exc:
            raise CustomerConflict("La cuenta ya está vinculada a otro perfil.") from exc
