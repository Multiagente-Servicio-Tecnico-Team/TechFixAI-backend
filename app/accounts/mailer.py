"""Envío del correo de restablecimiento: SMTP real o carpeta local (outbox) para desarrollo."""
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email" / "templates"
SUBJECT = "Restablece tu contraseña de TechFix.AI"

_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)


def render_password_reset(name: str, link: str, minutes: int) -> str:
    return _env.get_template("password_reset.html").render(name=name, link=link, minutes=minutes)


class OutboxMailer:
    """Guarda cada correo como archivo HTML en una carpeta local ignorada por git."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def send(self, to: str, subject: str, html: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{datetime.now():%Y%m%d-%H%M%S-%f}-password-reset.html"
        path.write_text(f"<!-- Para: {to} | Asunto: {subject} -->\n{html}", encoding="utf-8")
        return path


class SmtpMailer:
    """Usa el servicio SMTP existente del repositorio (variables SMTP_*)."""

    def send(self, to: str, subject: str, html: str) -> None:
        from app.email.email_service import _send_email_sync

        _send_email_sync(to, subject, html)


def build_mailer(mode: str, outbox_dir: str):
    return SmtpMailer() if mode == "smtp" else OutboxMailer(outbox_dir)


def send_password_reset(mailer, to: str, name: str, link: str, minutes: int) -> None:
    """Se ejecuta en segundo plano. Un fallo se registra sin correo, enlace ni token."""
    try:
        mailer.send(to, SUBJECT, render_password_reset(name, link, minutes))
    except Exception:  # noqa: BLE001 - el usuario ya recibió la respuesta genérica
        logger.error("Could not send the password reset email.")
