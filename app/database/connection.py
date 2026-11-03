import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import sessionmaker

from app.settings import load_settings


DATABASE_URL = load_settings().database_url


def _create_database_engine(database_url: str):
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+pg8000")
    return create_engine(url, pool_pre_ping=True)


engine = _create_database_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_engine():
    global DATABASE_URL, engine

    if engine is None:
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL no esta configurada en el archivo .env")
        engine = _create_database_engine(DATABASE_URL)
        SessionLocal.configure(bind=engine)

    return engine
