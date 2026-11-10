from langchain_core.tools import tool
from app.agents.decentralized.tools.soporte_tools import transferir_a_soporte as _support
from app.agents.decentralized.tools.ventas_tools import transferir_a_tecnico as _hardware
from app.agents.decentralized.tools.facturacion_tools import transferir_a_facturacion as _billing


@tool(description=_support.description)
def transfer_to_support(reason: str) -> str:
    return _support.invoke({"motivo": reason})


@tool(description=_hardware.description)
def transfer_to_hardware(reason: str) -> str:
    return _hardware.invoke({"motivo": reason})


@tool(description=_billing.description)
def transfer_to_billing(reason: str) -> str:
    return _billing.invoke({"motivo": reason})


legacy_handoff_tools = [_billing, _support, _hardware]
