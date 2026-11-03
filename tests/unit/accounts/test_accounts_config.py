import pytest

from app.accounts.config import Settings


@pytest.mark.parametrize(
    ("database_url", "expected_driver"),
    [
        ("postgresql://user:password@localhost:5432/techfix", "postgresql+pg8000"),
        ("postgres://user:password@localhost:5432/techfix", "postgresql+pg8000"),
        (
            "postgresql+pg8000://user:password@localhost:5432/techfix",
            "postgresql+pg8000",
        ),
    ],
)
def test_database_url_uses_declared_postgresql_driver(
    monkeypatch, database_url, expected_driver
):
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("AUTH_SECRET", "test-secret-value-with-at-least-32-chars")

    settings = Settings.from_env()

    assert settings.database_url.startswith(f"{expected_driver}://")


def test_database_url_is_optional(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_SECRET", "test-secret-value-with-at-least-32-chars")

    assert Settings.from_env().database_url is None
