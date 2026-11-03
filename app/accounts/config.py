"""Configuración del servicio de cuentas leída de variables de entorno."""
import logging
import os
import secrets
from dataclasses import dataclass, field

from sqlalchemy.engine import make_url

logger = logging.getLogger(__name__)


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    auth_secret: str
    secure_cookie: bool = True
    frontend_origins: tuple[str, ...] = ("http://localhost:5173",)
    session_hours: int = 8
    bcrypt_rounds: int = 12
    max_failed_logins: int = 5
    lockout_seconds: int = 15 * 60
    cookie_name: str = field(default="techfix_session")
    frontend_url: str = "http://localhost:5173"
    mail_mode: str = "outbox"
    reset_minutes: int = 15
    outbox_dir: str = ".local/outbox"
    max_reset_requests: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.getenv("AUTH_SECRET", "")
        if not secret:
            # Solo para desarrollo: las sesiones se invalidan al reiniciar el servidor.
            logger.warning("AUTH_SECRET is not set; using a temporary secret.")
            secret = secrets.token_urlsafe(48)
        if len(secret) < 32:
            raise RuntimeError("AUTH_SECRET must be at least 32 characters long.")
        origins = tuple(o.strip() for o in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if o.strip())
        rounds = int(os.getenv("BCRYPT_ROUNDS", "12"))
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            parsed_url = make_url(database_url)
            if parsed_url.drivername in {"postgres", "postgresql"}:
                database_url = parsed_url.set(
                    drivername="postgresql+pg8000"
                ).render_as_string(hide_password=False)
        return cls(
            database_url=database_url,
            auth_secret=secret,
            secure_cookie=_bool(os.getenv("AUTH_SECURE_COOKIE"), True),
            frontend_origins=origins,
            bcrypt_rounds=max(4, min(rounds, 15)),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/"),
            mail_mode="smtp" if os.getenv("MAIL_MODE", "outbox").strip().lower() == "smtp" else "outbox",
            reset_minutes=max(5, min(int(os.getenv("RESET_TOKEN_MINUTES", "15")), 60)),
            outbox_dir=os.getenv("OUTBOX_DIR", ".local/outbox"),
        )
