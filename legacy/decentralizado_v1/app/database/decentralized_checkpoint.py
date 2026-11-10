"""Optional technical checkpoint infrastructure. Import never connects or runs SQL."""
from dataclasses import dataclass, field
from math import isfinite
import os
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class CheckpointSettings:
    dsn: str | None = field(default=None, repr=False)
    schema: str = "langgraph_decentralized"
    min_size: int = 1
    max_size: int = 5
    timeout: float = 30.0
    connect_timeout: int = 10

    def __post_init__(self):
        if self.dsn is not None:
            try:
                url = urlsplit(self.dsn)
                valid = (isinstance(self.dsn, str) and url.scheme in {"postgres", "postgresql"}
                         and bool(url.hostname) and bool(url.path.strip("/")))
            except (ValueError, TypeError, AttributeError):
                valid = False
            if not valid:
                raise ValueError("DSN técnico PostgreSQL inválido") from None
        if (not isinstance(self.schema, str) or not re.fullmatch(r"[a-z_][a-z0-9_]*", self.schema)
                or self.schema in {"public", "information_schema"} or self.schema.startswith("pg_")):
            raise ValueError("Esquema técnico inválido")
        if (type(self.min_size) is not int or type(self.max_size) is not int
                or not 0 <= self.min_size <= self.max_size or self.max_size < 1):
            raise ValueError("Tamaños de pool inválidos")
        if type(self.timeout) not in {int, float} or not isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("Timeout de pool inválido")
        if type(self.connect_timeout) is not int or self.connect_timeout <= 0:
            raise ValueError("Timeout de conexión inválido")


def load_checkpoint_settings():
    """Reads independent technical settings; never falls back to DATABASE_URL."""
    def number(key, default, converter):
        try:
            return converter(os.environ.get(key, default))
        except (ValueError, TypeError):
            raise ValueError(f"Configuración inválida: {key}") from None
    return CheckpointSettings(
        dsn=os.environ.get("DECENTRALIZED_CHECKPOINT_DSN", "").strip() or None,
        schema=os.environ.get("DECENTRALIZED_CHECKPOINT_SCHEMA", "langgraph_decentralized"),
        min_size=number("DECENTRALIZED_CHECKPOINT_POOL_MIN", "1", int),
        max_size=number("DECENTRALIZED_CHECKPOINT_POOL_MAX", "5", int),
        timeout=number("DECENTRALIZED_CHECKPOINT_POOL_TIMEOUT", "30", float),
        connect_timeout=number("DECENTRALIZED_CHECKPOINT_CONNECT_TIMEOUT", "10", int),
    )


def _dependencies():
    try:
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool
        from langgraph.checkpoint.postgres import PostgresSaver
    except ImportError:
        raise RuntimeError("Faltan dependencias opcionales de requirements-checkpoint.txt") from None
    return ConnectionPool, PostgresSaver, dict_row


class CheckpointResources:
    """Owns an unopened pool and its saver. No setup or automatic connection."""
    def __init__(self, pool, saver):
        self.pool = pool
        self.saver = saver
        self._closed = False

    def close(self):
        if not self._closed:
            try:
                self.pool.close()
            except Exception:
                raise RuntimeError("No fue posible cerrar el pool técnico") from None
            self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError("Recursos técnicos cerrados")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


def build_checkpoint_resources(settings: CheckpointSettings):
    """Constructs only; a later authorized lifecycle must open the pool explicitly."""
    if not settings.dsn:
        raise ValueError("Falta DECENTRALIZED_CHECKPOINT_DSN")
    pool_type, saver_type, dict_row = _dependencies()
    pool = None
    try:
        pool = pool_type(conninfo=settings.dsn, min_size=settings.min_size,
                         max_size=settings.max_size, timeout=settings.timeout, open=False,
                         kwargs={"autocommit": True, "row_factory": dict_row,
                                 "connect_timeout": settings.connect_timeout,
                                 "options": f"-csearch_path={settings.schema}"})
        saver = saver_type(pool)
    except Exception:
        if pool is not None:
            try:
                pool.close()
            except Exception:
                pass
        raise RuntimeError("No fue posible construir los recursos técnicos de checkpoint") from None
    return CheckpointResources(pool, saver)
