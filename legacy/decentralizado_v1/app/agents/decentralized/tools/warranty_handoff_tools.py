from langchain_core.tools import tool
from app.agents.decentralized.tools.garantia_tools import transferir_a_logistica as _logistics
from app.agents.decentralized.tools.garantia_tools import transferir_a_soporte as _support


@tool(description=_logistics.description)
def transfer_to_logistics(reason: str) -> str:
    return _logistics.invoke({"motivo": reason})


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


legacy_handoff_tools = [_logistics, _support]
warranty_handoff_tools = [transfer_to_logistics, transfer_to_support]
