from langchain_core.tools import tool
from app.agents.decentralized.tools.logistica_tools import transferir_a_soporte as _support


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


legacy_handoff_tools = [_support]
