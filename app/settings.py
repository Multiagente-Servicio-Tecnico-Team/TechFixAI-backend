import os
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None = field(repr=False)
    groq_model: str | None
    database_url: str | None = field(repr=False)
    langsmith_api_key: str | None = field(repr=False)
    langsmith_tracing: bool
    langsmith_project: str
    langsmith_hide_inputs: bool
    langsmith_hide_outputs: bool
    labor_maintenance_price: Decimal
    labor_diagnosis_price: Decimal
    labor_pc_build_price: Decimal = Decimal("50.00")
    audio_transcription_enabled: bool = False
    audio_transcription_timeout_seconds: float = 30.0
    audio_max_bytes: int = 25_000_000
    audio_max_duration_ms: int = 120_000
    audio_requests_per_minute: int = 5
    rag_retrieval_mode: str = "lexical"

    def require_chat_configuration(self) -> None:
        missing = []
        if not self.groq_api_key:
            missing.append("GROQ_API_KEY")
        if not self.groq_model:
            missing.append("GROQ_MODEL")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if self.langsmith_tracing and not self.langsmith_api_key:
            missing.append("LANGSMITH_API_KEY (requerida con LANGSMITH_TRACING=true)")
        if missing:
            raise RuntimeError(
                "Falta configurar: " + ", ".join(missing) + ". "
                "Revisa las variables del archivo .env."
            )

    def labor_price_for(self, task_type: str) -> Decimal:
        if task_type == "sale":
            return Decimal("0.00")
        if task_type == "pc_build":
            return self.labor_pc_build_price
        if task_type == "maintenance":
            return self.labor_maintenance_price
        if task_type == "diagnosis":
            return self.labor_diagnosis_price
        raise ValueError(f"Tipo de trabajo no reconocido: {task_type}.")


def _optional_decimal(name: str) -> Decimal | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} debe ser un importe decimal válido.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{name} debe ser un importe decimal no negativo.")
    return amount


def _labor_price(name: str, default: str) -> Decimal:
    amount = _optional_decimal(name)
    if amount is None:
        return Decimal(default)
    if amount <= 0:
        raise ValueError(f"{name} debe ser un importe decimal positivo.")
    return amount


def _environment_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{name} debe ser true o false.")


def _positive_integer(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero positivo.") from exc
    if parsed <= 0:
        raise ValueError(f"{name} debe ser un entero positivo.")
    return parsed


def _positive_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un numero positivo.") from exc
    if not 0 < parsed < float("inf"):
        raise ValueError(f"{name} debe ser un numero positivo.")
    return parsed


def _rag_retrieval_mode() -> str:
    value = os.getenv("RAG_RETRIEVAL_MODE", "lexical").strip().lower()
    if value not in {"lexical", "hybrid"}:
        raise ValueError("RAG_RETRIEVAL_MODE debe ser lexical o hybrid.")
    return value


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip() or None,
        groq_model=os.getenv("GROQ_MODEL", "").strip() or None,
        database_url=os.getenv("DATABASE_URL", "").strip() or None,
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", "").strip() or None,
        langsmith_tracing=_environment_flag("LANGSMITH_TRACING", default=False),
        langsmith_project=os.getenv(
            "LANGSMITH_PROJECT",
            "Sistema-Multiagente-de-Servicio-Tecnico-Ventas-y-Soporte",
        ).strip(),
        langsmith_hide_inputs=_environment_flag(
            "LANGSMITH_HIDE_INPUTS",
            default=True,
        ),
        langsmith_hide_outputs=_environment_flag(
            "LANGSMITH_HIDE_OUTPUTS",
            default=True,
        ),
        labor_maintenance_price=_labor_price(
            "LABOR_MAINTENANCE_PRICE",
            "35.00",
        ),
        labor_diagnosis_price=_labor_price(
            "LABOR_DIAGNOSIS_PRICE",
            "50.00",
        ),
        labor_pc_build_price=_labor_price(
            "LABOR_PC_BUILD_PRICE",
            "50.00",
        ),
        audio_transcription_enabled=_environment_flag("AUDIO_TRANSCRIPTION_ENABLED", default=False),
        audio_transcription_timeout_seconds=_positive_float("AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS", 30.0),
        audio_max_bytes=_positive_integer("AUDIO_MAX_BYTES", 25_000_000),
        audio_max_duration_ms=_positive_integer("AUDIO_MAX_DURATION_MS", 120_000),
        audio_requests_per_minute=_positive_integer("AUDIO_REQUESTS_PER_MINUTE", 5),
        rag_retrieval_mode=_rag_retrieval_mode(),
    )
