"""Pruebas de /recuperar y /restablecer con SQLite en memoria y un correo simulado."""
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app
from app.accounts.config import Settings
from app.accounts.mailer import OutboxMailer, render_password_reset
from app.accounts.models import Base, RecoveryToken, User

PASSWORD = "TriageTech#2026"
NEW_PASSWORD = "NuevaClave#2026"
EMAIL = "martin.gomez@gmail.com"
SENT = {"detail": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.fail = False

    def send(self, to, subject, html):
        if self.fail:
            raise ConnectionError("SMTP caído")
        self.sent.append({"to": to, "subject": subject, "html": html})

    def last_token(self):
        html = self.sent[-1]["html"]
        start = html.index("http://localhost:5173/portal/restablecer?token=")
        url = html[start:html.index('"', start)]
        return parse_qs(urlparse(url).query)["token"][0]


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False, bcrypt_rounds=4)
    mailer = FakeMailer()
    client = TestClient(create_app(settings, factory, mailer=mailer))
    client.post("/registro", json={"nombre": "Martín Gómez", "email": EMAIL, "telefono": "+51987654321", "password": PASSWORD})
    return client, factory, mailer


def tokens(factory):
    with factory() as db:
        return db.scalars(select(RecoveryToken).order_by(RecoveryToken.id)).all()


def login(client, password):
    return client.post("/login", json={"email": EMAIL, "password": password})


# ---------- POST /recuperar ----------

def test_same_response_whether_or_not_account_exists(env):
    client, _, mailer = env
    existing = client.post("/recuperar", json={"email": "MARTIN.GOMEZ@gmail.com"})
    missing = client.post("/recuperar", json={"email": "nadie@techfix.ai"})

    assert existing.status_code == missing.status_code == 200
    assert existing.json() == missing.json() == SENT
    assert len(mailer.sent) == 1 and mailer.sent[0]["to"] == EMAIL
    assert "token" not in existing.text


def test_stores_only_token_hash_and_sends_link(env):
    client, factory, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    raw = mailer.last_token()
    [row] = tokens(factory)

    assert row.token == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in row.token and len(raw) >= 40
    assert row.used is False
    expires = row.expires_at.replace(tzinfo=timezone.utc)
    assert timedelta(minutes=14) < expires - datetime.now(timezone.utc) <= timedelta(minutes=15)
    assert "Hola Martín" in mailer.sent[0]["html"] and "15 minutos" in mailer.sent[0]["html"]


def test_invalid_email_returns_422(env):
    client, _, mailer = env
    res = client.post("/recuperar", json={"email": "no-es-correo"})
    assert res.status_code == 422 and res.json()["field"] == "email"
    assert mailer.sent == []


def test_inactive_account_gets_no_email(env):
    client, factory, mailer = env
    with factory() as db:
        db.execute(update(User).values(active=False))
        db.commit()
    assert client.post("/recuperar", json={"email": EMAIL}).json() == SENT
    assert mailer.sent == [] and tokens(factory) == []


def test_request_limit_per_email(env):
    client, _, _ = env
    for _ in range(5):
        assert client.post("/recuperar", json={"email": EMAIL}).status_code == 200
    assert client.post("/recuperar", json={"email": EMAIL}).status_code == 429


def test_email_failure_does_not_change_response(env):
    client, _, mailer = env
    mailer.fail = True
    res = client.post("/recuperar", json={"email": EMAIL})
    assert res.status_code == 200 and res.json() == SENT


# ---------- POST /restablecer ----------

def test_reset_makes_only_new_password_valid(env):
    client, factory, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    res = client.post("/restablecer", json={"token": mailer.last_token(), "password": NEW_PASSWORD})

    assert res.status_code == 200 and res.json() == {"detail": "Contraseña actualizada."}
    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200
    assert all(t.used for t in tokens(factory))


def test_link_can_be_used_only_once(env):
    client, _, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    token = mailer.last_token()
    assert client.post("/restablecer", json={"token": token, "password": NEW_PASSWORD}).status_code == 200
    again = client.post("/restablecer", json={"token": token, "password": "OtraClave#2026"})
    assert again.status_code == 410
    assert again.json() == {"detail": "El enlace no es válido o ya expiró.", "code": "invalid_token"}


def test_only_latest_requested_link_is_valid(env):
    client, _, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    first = mailer.last_token()
    client.post("/recuperar", json={"email": EMAIL})
    second = mailer.last_token()

    assert client.post("/restablecer", json={"token": first, "password": NEW_PASSWORD}).status_code == 410
    assert client.post("/restablecer", json={"token": second, "password": NEW_PASSWORD}).status_code == 200


def test_expired_link(env):
    client, factory, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    with factory() as db:
        db.execute(update(RecoveryToken).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    assert client.post("/restablecer", json={"token": mailer.last_token(), "password": NEW_PASSWORD}).status_code == 410
    assert login(client, PASSWORD).status_code == 200


def test_unknown_token(env):
    client, _, _ = env
    res = client.post("/restablecer", json={"token": "x" * 43, "password": NEW_PASSWORD})
    assert res.status_code == 410 and res.json()["code"] == "invalid_token"


def test_weak_password_does_not_consume_link(env):
    client, _, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    token = mailer.last_token()
    weak = client.post("/restablecer", json={"token": token, "password": "debil"})

    assert weak.status_code == 422 and weak.json()["field"] == "password"
    assert "debil" not in weak.text
    assert client.post("/restablecer", json={"token": token, "password": NEW_PASSWORD}).status_code == 200


def test_account_deactivated_after_requesting_link(env):
    client, factory, mailer = env
    client.post("/recuperar", json={"email": EMAIL})
    with factory() as db:
        db.execute(update(User).values(active=False))
        db.commit()
    assert client.post("/restablecer", json={"token": mailer.last_token(), "password": NEW_PASSWORD}).status_code == 410


def test_reset_closes_open_sessions(env):
    client, _, mailer = env
    assert login(client, PASSWORD).status_code == 200
    assert client.get("/me").status_code == 200

    client.post("/recuperar", json={"email": EMAIL})
    client.post("/restablecer", json={"token": mailer.last_token(), "password": NEW_PASSWORD})

    assert client.get("/me").status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200
    assert client.get("/me").status_code == 200


def test_reset_clears_failed_attempts(env):
    client, _, mailer = env
    for _ in range(5):
        login(client, "Mala#2026")
    assert login(client, PASSWORD).status_code == 429
    client.post("/recuperar", json={"email": EMAIL})
    client.post("/restablecer", json={"token": mailer.last_token(), "password": NEW_PASSWORD})
    assert login(client, NEW_PASSWORD).status_code == 200


# ---------- Correo ----------

def test_outbox_saves_email_to_file(tmp_path):
    path = OutboxMailer(tmp_path).send("ana@demo.pe", "Asunto", "<p>hola</p>")
    content = path.read_text(encoding="utf-8")
    assert path.parent == tmp_path and "Para: ana@demo.pe" in content and "<p>hola</p>" in content


def test_template_escapes_name():
    html = render_password_reset("<script>alert(1)</script>", "http://localhost:5173/portal/restablecer?token=abc", 15)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
