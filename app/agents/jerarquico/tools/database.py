"""Read-only, parameterized tools backed by the shared repository."""

import json
from typing import Any

from langchain_core.tools import StructuredTool

from app.database.repository import ServiceRepository


def make_warranty_lookup_tool(repository: ServiceRepository) -> StructuredTool:
    def lookup_warranty(warranty_code: str) -> str:
        """Consulta una póliza mediante su código exacto."""
        result: dict[str, Any] | None = repository.find_warranty(warranty_code)
        return json.dumps(result, default=str, ensure_ascii=False)

    return StructuredTool.from_function(
        func=lookup_warranty,
        name="consultar_garantia_por_codigo",
        description="Consulta la póliza de garantía por su código exacto.",
    )
