import os

from dotenv import load_dotenv


load_dotenv()
CURRENCY = os.getenv("CURRENCY", "PEN").upper()
CURRENCY_SYMBOL = "S/" if CURRENCY == "PEN" else CURRENCY


def configure_tracing() -> None:
    tracing_enabled = os.getenv("LANGSMITH_TRACING", "true").lower()
    os.environ["LANGSMITH_TRACING"] = tracing_enabled
    os.environ["LANGCHAIN_TRACING_V2"] = tracing_enabled
    os.environ.setdefault(
        "LANGSMITH_PROJECT",
        "Sistema-Multiagente-de-Servicio-Tecnico-Ventas-y-Soporte",
    )


def create_chat_model():
    from app.adapters.llm.model_factory import create_model
    from app.settings import load_settings

    settings = load_settings()
    configure_tracing()
    return create_model(settings)
