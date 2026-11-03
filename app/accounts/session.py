"""Sesión reutilizable: cualquier API del equipo identifica al usuario con la cookie del login.

Uso en la API de un patrón LangGraph:

    guard = SessionGuard.from_env()
    guard.install(app)

    @app.post("/api/chat")
    def chat(body: ChatIn, customer: SessionCustomer = Depends(guard.require_customer)):
        ...  # customer.id va a tickets.customer_id

La identidad sale solo de la cookie firmada; nunca del cuerpo de la petición.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.accounts.config import Settings
from app.accounts.models import Role, User
from app.accounts.security import password_fingerprint, read_session

SESSION_REQUIRED = "Inicia sesión para continuar."
CUSTOMER_ONLY = "El chat es para clientes."
ADMIN_ONLY = "Esta operación requiere una cuenta administradora."


class SessionError(Exception):
    def __init__(self, status: int, detail: str, code: str):
        super().__init__(detail)
        self.status, self.detail, self.code = status, detail, code


@dataclass(frozen=True)
class SessionCustomer:
    id: int
    first_name: str
    last_name: str | None
    email: str
    role: str


def _to_customer(user: User) -> SessionCustomer:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return SessionCustomer(id=user.id, first_name=user.name, last_name=user.last_name, email=user.email, role=role)


class SessionGuard:
    def __init__(self, settings: Settings, session_factory: sessionmaker):
        self.settings = settings
        self.session_factory = session_factory

    @classmethod
    def from_env(cls, session_factory: sessionmaker | None = None) -> "SessionGuard":
        """Para otras APIs: exige el mismo AUTH_SECRET y DATABASE_URL que la API de cuentas."""
        load_dotenv()
        if not os.getenv("AUTH_SECRET"):
            raise RuntimeError("AUTH_SECRET must match the one used by the accounts API.")
        settings = Settings.from_env()
        if session_factory is None:
            if not settings.database_url:
                raise RuntimeError("DATABASE_URL is not configured.")
            engine = create_engine(settings.database_url, pool_pre_ping=True)
            session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return cls(settings, session_factory)

    def resolve(self, request: Request) -> User | None:
        """Usuario activo de la cookie, o None si falta, es inválida, venció o la contraseña cambió."""
        session = read_session(request.cookies.get(self.settings.cookie_name), self.settings.auth_secret)
        if not session:
            return None
        with self.session_factory() as db:
            user = db.get(User, session[0])
            if user is None or not user.active:
                return None
            if session[1] != password_fingerprint(user.password_hash, self.settings.auth_secret):
                return None
            db.expunge(user)
            return user

    def require_user(self, request: Request) -> SessionCustomer:
        user = self.resolve(request)
        if user is None:
            raise SessionError(401, SESSION_REQUIRED, "session_required")
        return _to_customer(user)

    def require_customer(self, request: Request) -> SessionCustomer:
        customer = self.require_user(request)
        if customer.role != Role.CUSTOMER.value:
            raise SessionError(403, CUSTOMER_ONLY, "customer_only")
        return customer

    def require_admin(self, request: Request) -> SessionCustomer:
        administrator = self.require_user(request)
        if administrator.role != Role.ADMIN.value:
            raise SessionError(403, ADMIN_ONLY, "admin_only")
        return administrator

    @staticmethod
    def install(app: FastAPI) -> None:
        @app.exception_handler(SessionError)
        async def on_session_error(_request: Request, exc: SessionError):
            return JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code})
