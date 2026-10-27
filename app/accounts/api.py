"""API de cuentas: registro, inicio y cierre de sesión, recuperación y restablecimiento de contraseña.

Las rutas públicas (/registro, /login, /recuperar, /restablecer) y sus claves JSON son el contrato del equipo.

Ejecutar:  uvicorn app.accounts.api:create_app --factory --host localhost --port 8000
"""
import logging
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.config import Settings
from app.accounts.mailer import build_mailer, send_password_reset
from app.accounts.models import User
from app.accounts.schemas import (
    FULL_NAME_ERROR,
    LoginIn,
    PasswordRecoveryIn,
    PasswordResetIn,
    RegisterIn,
    UserResponse,
)
from app.accounts.security import LoginLimiter, dummy_hash, password_fingerprint, read_session, sign_session
from app.accounts.service import (
    EmailAlreadyRegistered,
    authenticate,
    register_user,
    request_password_reset,
    reset_password,
    to_out,
)

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Correo o contraseña incorrectos."
TOO_MANY = "Demasiados intentos. Espera unos minutos antes de volver a intentar."
RESET_SENT = "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."
INVALID_TOKEN = "El enlace no es válido o ya expiró."


def _validation_response(exc: RequestValidationError) -> JSONResponse:
    """422 sin devolver los valores enviados (podrían incluir la contraseña)."""
    errors = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ()) if part != "body"]
        message = str(err.get("msg", "Valor inválido.")).removeprefix("Value error, ")
        field_name = loc[0] if loc else ("nombre" if err.get("type") == FULL_NAME_ERROR else None)
        # "campo" y "mensaje" son las claves JSON del contrato de errores que usa el frontend.
        errors.append({"campo": field_name, "mensaje": message})
    field = next((e["campo"] for e in errors if e["campo"]), None)
    return JSONResponse(status_code=422, content={"detail": "Datos inválidos.", "field": field, "errors": errors})


def create_app(settings: Settings | None = None, session_factory: sessionmaker | None = None, mailer=None) -> FastAPI:
    load_dotenv()
    settings = settings or Settings.from_env()
    if session_factory is None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    app = FastAPI(title="TechFix.AI · Cuentas", version="1.0.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.limiter = LoginLimiter(settings.max_failed_logins, settings.lockout_seconds)
    app.state.reset_limiter = LoginLimiter(settings.max_reset_requests, settings.lockout_seconds)
    app.state.mailer = mailer or build_mailer(settings.mail_mode, settings.outbox_dir)
    fallback_hash = dummy_hash(settings.bcrypt_rounds)
    max_age = settings.session_hours * 3600

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_request: Request, exc: RequestValidationError):
        return _validation_response(exc)

    @app.exception_handler(OperationalError)
    async def on_db_unavailable(_request: Request, _exc: OperationalError):
        logger.error("Database unavailable")
        return JSONResponse(status_code=503, content={"detail": "Servicio no disponible. Inténtalo más tarde."})

    def get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def set_session_cookie(response: Response, user: User) -> None:
        response.set_cookie(
            settings.cookie_name,
            sign_session(user.id, settings.auth_secret, max_age, password_fingerprint(user.password_hash, settings.auth_secret)),
            max_age=max_age,
            httponly=True,
            secure=settings.secure_cookie,
            samesite="lax",
            path="/",
        )

    @app.post("/registro", status_code=201, response_model=UserResponse)
    def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
        try:
            user = register_user(db, body, settings.bcrypt_rounds)
        except EmailAlreadyRegistered:
            return JSONResponse(status_code=409, content={"detail": "El correo ya está registrado.", "field": "email"})
        # El portal entra directo tras el registro: abre la misma sesión que /login.
        set_session_cookie(response, user)
        return UserResponse(user=to_out(user))

    @app.post("/login", response_model=UserResponse)
    def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
        limiter: LoginLimiter = app.state.limiter
        if limiter.blocked(body.email):
            return JSONResponse(status_code=429, content={"detail": TOO_MANY})
        user = authenticate(db, body.email, body.password, fallback_hash)
        if user is None:
            limiter.fail(body.email)
            return JSONResponse(status_code=401, content={"detail": INVALID_CREDENTIALS})
        limiter.reset(body.email)
        set_session_cookie(response, user)
        return UserResponse(user=to_out(user))

    @app.post("/logout", status_code=204)
    def logout():
        response = Response(status_code=204)
        response.delete_cookie(settings.cookie_name, path="/", httponly=True, secure=settings.secure_cookie, samesite="lax")
        return response

    @app.get("/me", response_model=UserResponse)
    def me(request: Request, db: Session = Depends(get_db)):
        session = read_session(request.cookies.get(settings.cookie_name), settings.auth_secret)
        user = db.get(User, session[0]) if session else None
        # Una cookie emitida antes de cambiar la contraseña ya no es válida.
        if user is None or not user.active or session[1] != password_fingerprint(user.password_hash, settings.auth_secret):
            return JSONResponse(status_code=401, content={"detail": "Sesión no válida o vencida."})
        return UserResponse(user=to_out(user))

    @app.post("/recuperar")
    def recover_password(body: PasswordRecoveryIn, background: BackgroundTasks, db: Session = Depends(get_db)):
        reset_limiter: LoginLimiter = app.state.reset_limiter
        if reset_limiter.blocked(body.email):
            return JSONResponse(status_code=429, content={"detail": TOO_MANY})
        reset_limiter.fail(body.email)
        result = request_password_reset(db, body.email, settings.reset_minutes)
        if result is not None:
            user, raw_token = result
            link = f"{settings.frontend_url}/portal/restablecer?token={quote(raw_token)}"
            # El envío va en segundo plano: la respuesta tarda lo mismo exista o no la cuenta.
            background.add_task(send_password_reset, app.state.mailer, user.email, user.name, link, settings.reset_minutes)
        return {"detail": RESET_SENT}

    @app.post("/restablecer")
    def confirm_password_reset(body: PasswordResetIn, db: Session = Depends(get_db)):
        user = reset_password(db, body.token, body.password, settings.bcrypt_rounds)
        if user is None:
            return JSONResponse(status_code=410, content={"detail": INVALID_TOKEN, "code": "invalid_token"})
        app.state.limiter.reset(user.email)
        return {"detail": "Contraseña actualizada."}

    @app.get("/salud")
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        # "estado" y "bd" son las claves JSON que verifica la colección de Postman.
        return {"estado": "ok", "bd": "ok"}

    return app
