"""Inventario único de fuentes Markdown para los tres patrones."""
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    path: Path
    area: str
    trust_level: str
    audience: str = "customer"
    language: str = "es"
    version: str = "1"
    customer_facts_allowed: bool = True


def knowledge_sources() -> tuple[KnowledgeSource, ...]:
    roots = (
        ("business", BASE_DIR / "data" / "knowledge", "verified_guide", True),
        (
            "hierarchical",
            BASE_DIR / "app" / "agents" / "jerarquico" / "knowledge_base",
            "verified_guide",
            True,
        ),
        (
            "orchestrator",
            BASE_DIR / "app" / "agents" / "orquestador" / "knowledge",
            "verified_guide",
            True,
        ),
    )
    sources: list[KnowledgeSource] = []
    for source_group, root, trust, customer_facts_allowed in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.md")):
            relative = path.relative_to(root).as_posix()
            source_id = f"{source_group}:{relative.rsplit('.', 1)[0]}"
            area = "faq" if path.name.casefold().startswith("faq") else (
                "sales" if "build" in path.name.casefold() else "technical"
            )
            trust_level = "demo_only" if area == "faq" else trust
            sources.append(
                KnowledgeSource(
                    source_id=source_id,
                    path=path,
                    area=area,
                    trust_level=trust_level,
                    customer_facts_allowed=customer_facts_allowed and trust_level != "demo_only",
                )
            )
    return tuple(sources)
