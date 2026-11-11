import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from langchain_core.documents import Document

from app.rag.retriever import retrieve_documents


KNOWLEDGE_BASE_PATH = Path(__file__).parent / "knowledge_base"
_CASE_PATTERN = re.compile(
    r"(?m)^\s*(?:[-*]\s*)?\*\*Caso\s+(\d+):\s*(.*?)\*\*\s*$"
    r"|^\s*#{2,4}\s+Caso\s+(\d+):\s*(.*?)\s*$",
    re.IGNORECASE,
)
_FIELD_PATTERN = re.compile(
    r"(?im)^\s*[-*]?\s*\*\*"
    r"(Diagn[oó]stico|Soluci[oó]n|Componente\s*/\s*Servicio|Palabras\s+clave)"
    r"\*\*\s*:\s*(.*?)\s*$"
)
class CatalogItem(BaseModel):
    identifier: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    keywords: list[str]
    diagnosis: str
    solution: str
    recommended_parts: list[CatalogItem]
    selection_mode: Literal["all", "one"]


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()



def _parse_case(
    *,
    source: Path,
    number: str,
    title: str,
    content: str,
) -> KnowledgeDocument:
    fields: dict[str, str] = {}
    for match in _FIELD_PATTERN.finditer(content):
        label = _normalize(match.group(1))
        fields[label] = match.group(2).strip()

    diagnosis = fields.get("diagnostico", "")
    solution = fields.get("solucion", "")
    components = fields.get("componente servicio", "")
    if not diagnosis or not solution or not components:
        raise ValueError(
            f"El caso {number} de {source} debe incluir Diagnóstico, "
            "Solución y Componente/Servicio."
        )

    identifiers = re.findall(r"`([^`]+)`", components)
    if not identifiers:
        raise ValueError(
            f"El caso {number} de {source} debe escribir los códigos de "
            "Componente/Servicio entre acentos graves (`código`)."
        )

    reason = re.sub(r"\s+", " ", diagnosis).strip()
    items = [
        CatalogItem(identifier=identifier.strip(), reason=reason)
        for identifier in identifiers
    ]
    explicit_keywords = fields.get("palabras clave", "")
    keywords = [
        value.strip()
        for value in re.split(r"[,;]", explicit_keywords)
        if value.strip()
    ]
    keywords.extend([title, diagnosis, solution])

    return KnowledgeDocument(
        id=f"{source.stem}:{int(number):03d}",
        title=title.strip(),
        keywords=keywords,
        diagnosis=diagnosis,
        solution=solution,
        recommended_parts=items,
        selection_mode=(
            "one"
            if re.search(r"\s+o\s+", components, re.IGNORECASE)
            else "all"
        ),
    )


def _load_markdown_file(path: Path) -> list[KnowledgeDocument]:
    content = path.read_text(encoding="utf-8")
    matches = list(_CASE_PATTERN.finditer(content))
    documents = []
    for index, match in enumerate(matches):
        number = match.group(1) or match.group(3)
        title = match.group(2) or match.group(4)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        documents.append(
            _parse_case(
                source=path,
                number=number,
                title=title,
                content=content[start:end],
            )
        )
    return documents


@lru_cache(maxsize=1)
def load_knowledge_documents() -> tuple[KnowledgeDocument, ...]:
    if not KNOWLEDGE_BASE_PATH.is_dir():
        raise FileNotFoundError(
            f"No se encontró el directorio de conocimiento Markdown: "
            f"{KNOWLEDGE_BASE_PATH}"
        )

    paths = sorted(KNOWLEDGE_BASE_PATH.rglob("*.md"))
    documents = tuple(
        document
        for path in paths
        for document in _load_markdown_file(path)
    )
    if not documents:
        raise ValueError(
            f"No se encontraron casos estructurados en archivos Markdown de "
            f"{KNOWLEDGE_BASE_PATH}."
        )
    return documents


class MarkdownKnowledgeRetriever:
    def __init__(
        self,
        documents: tuple[KnowledgeDocument, ...] | None = None,
    ) -> None:
        self._documents = (
            load_knowledge_documents() if documents is None else documents
        )

    def retrieve(self, query: str, *, limit: int = 3) -> list[KnowledgeDocument]:
        if limit < 1:
            raise ValueError("El límite de recuperación debe ser mayor que cero.")
        by_source = {f"hierarchical:manual_servicio#{item.id}": item for item in self._documents}
        searchable = [
            Document(
                page_content="\n".join(
                    [item.title, *item.keywords, item.diagnosis, item.solution]
                ),
                metadata={
                    "source_id": f"hierarchical:manual_servicio#{item.id}",
                    "source_refs": "hierarchical:manual_servicio",
                    "source_path": "app/agents/jerarquico/knowledge_base/manual_servicio.md",
                    "title": item.title,
                    "area": "technical",
                    "trust_level": "verified_guide",
                    "audience": "customer",
                    "language": "es",
                    "content_digest": item.id,
                },
            )
            for item in self._documents
        ]
        passages = retrieve_documents(
            query,
            documents=searchable,
            allowed_sources={"hierarchical:manual_servicio"},
            allowed_areas={"technical"},
            allowed_trust_levels={"verified_guide"},
            limit=limit,
        )
        return [by_source[item.source_id] for item in passages if item.source_id in by_source]

    @staticmethod
    def format_context(documents: list[KnowledgeDocument]) -> str:
        if not documents:
            return (
                "No se encontraron casos pertinentes en los manuales Markdown. "
                "Formula una evaluación prudente usando solo los síntomas."
            )
        cases: list[str] = []
        for document in documents:
            part_lines = [
                f"- `{part.identifier}`: {part.reason}"
                for part in document.recommended_parts
            ]
            selection = (
                "Selecciona exactamente uno de los identificadores."
                if document.selection_mode == "one"
                else "Se requieren todos los identificadores listados."
            )
            cases.append(
                "\n".join(
                    [
                        f"Caso {document.id}: {document.title}",
                        f"Diagnóstico posible (no confirmado): {document.diagnosis}",
                        f"Guía técnica: {document.solution}",
                        "Artículos/servicios candidatos del catálogo PostgreSQL:",
                        *part_lines,
                        selection,
                    ]
                )
            )
        return (
            "\n\n".join(cases)
            + "\n\nLos manuales no definen precios ni stock. Usa únicamente el "
            "catálogo PostgreSQL; si no hay coincidencia inequívoca, stock o "
            "precio mayor que cero, no emitas una cotización."
        )

    @staticmethod
    def as_state(documents: list[KnowledgeDocument]) -> list[dict[str, Any]]:
        return [document.model_dump(mode="json") for document in documents]
