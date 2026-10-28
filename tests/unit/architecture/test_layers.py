"""Regla de dependencias de Clean Architecture: las capas internas no conocen a las externas."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FRAMEWORKS = ("fastapi", "starlette", "sqlalchemy", "langgraph", "langchain", "langchain_core", "groq", "langsmith", "pydantic")
OUTER_LAYERS = ("app.adapters", "app.infrastructure", "app.agents", "app.database", "app.accounts", "app.main")

RULES = {
    "app/domain": {"forbidden": FRAMEWORKS + OUTER_LAYERS + ("app.application",)},
    "app/application": {"forbidden": FRAMEWORKS + OUTER_LAYERS},
}


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def violations(layer: str) -> list[str]:
    forbidden = RULES[layer]["forbidden"]
    found = []
    for path in sorted((ROOT / layer).rglob("*.py")):
        for name in imports_of(path):
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                found.append(f"{path.relative_to(ROOT).as_posix()} importa {name}")
    return found


@pytest.mark.parametrize("layer", sorted(RULES))
def test_layer_does_not_depend_on_outer_layers_or_frameworks(layer):
    assert (ROOT / layer).is_dir()
    assert violations(layer) == []


def test_main_only_delegates_to_composition_root():
    names = imports_of(ROOT / "app/main.py")
    assert "app.infrastructure.chat_app" in names
    assert not any(name.startswith("app.agents") for name in names)
