"""Reglas de registro, inicio de sesión y restablecimiento de contraseña."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.models import RecoveryToken, User
from app.accounts.schemas import RegisterIn, UserOut
from app.accounts.security import hash_password, hash_reset_token, new_reset_token, verify_password


class EmailAlreadyRegistered(Exception):
    pass


def to_out(user: User) -> UserOut:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return UserOut(id=user.id, first_name=user.name, last_name=user.last_name, email=user.email, role=role)


def find_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def register_user(db: Session, data: RegisterIn, rounds: int) -> User:
    """Crea un cliente. El rol queda en CUSTOMER por el valor por defecto de la tabla."""
    if find_by_email(db, data.email):
        raise EmailAlreadyRegistered()
    user = User(
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password, rounds),
        name=data.first_name,
        last_name=data.last_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        # Dos registros simultáneos con el mismo correo: lo resuelve la restricción UNIQUE.
        db.rollback()
        raise EmailAlreadyRegistered() from exc
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str, fallback_hash: str) -> User | None:
    """Devuelve el usuario activo si la contraseña coincide. Siempre ejecuta una verificación bcrypt."""
    user = find_by_email(db, email)
    if user is None:
        verify_password(password, fallback_hash)
        return None
    if not verify_password(password, user.password_hash) or not user.active:
        return None
    return user


def _utc(value: datetime) -> datetime:
    # SQLite devuelve fechas sin zona; PostgreSQL (timestamptz) con zona.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _invalidate_tokens(db: Session, user_id: int) -> None:
    db.execute(
        update(RecoveryToken)
        .where(RecoveryToken.user_id == user_id, RecoveryToken.used.is_(False))
        .values(used=True)
    )


def request_password_reset(db: Session, email: str, minutes: int) -> tuple[User, str] | None:
    """Crea un token si la cuenta existe y está activa. Devuelve (usuario, token del enlace) o None.

    Solo el último enlace vale: los tokens pendientes anteriores se marcan como usados.
    """
    user = find_by_email(db, email)
    if user is None or not user.active:
        return None
    _invalidate_tokens(db, user.id)
    raw, digest = new_reset_token()
    db.add(RecoveryToken(user_id=user.id, token=digest, expires_at=datetime.now(timezone.utc) + timedelta(minutes=minutes)))
    db.commit()
    return user, raw


def reset_password(db: Session, raw_token: str, new_password: str, rounds: int) -> User | None:
    """Cambia la contraseña si el token es válido, vigente y sin usar. Devuelve el usuario o None."""
    row = db.scalar(select(RecoveryToken).where(RecoveryToken.token == hash_reset_token(raw_token)))
    now = datetime.now(timezone.utc)
    if row is None or row.used or _utc(row.expires_at) <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.active:
        return None
    # Marcado condicional: si dos peticiones usan el mismo enlace a la vez, solo una gana.
    claimed = db.execute(
        update(RecoveryToken).where(RecoveryToken.id == row.id, RecoveryToken.used.is_(False)).values(used=True)
    )
    if claimed.rowcount != 1:
        db.rollback()
        return None
    user.password_hash = hash_password(new_password, rounds)
    user.updated_at = now
    _invalidate_tokens(db, user.id)
    db.commit()
    return user
