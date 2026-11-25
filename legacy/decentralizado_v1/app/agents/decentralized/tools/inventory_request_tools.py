from langchain_core.tools import tool
from app.agents.decentralized.tools.ventas_tools import solicitar_inventario as _request


@tool(description=_request.description)
def request_inventory(query: str) -> dict:
    return _request.invoke({"consulta": query})


legacy_inventory_request_tools = [_request]
