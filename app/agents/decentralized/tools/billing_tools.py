"""Financial handoffs and actual capabilities; no commercial write tools enabled."""
from langchain_core.tools import StructuredTool, tool
from app.agents.decentralized.tools.software_tools import transferir_a_soporte as _support
from app.agents.decentralized.tools.soporte_tools import transferir_a_ventas as _sales


@tool
def transferir_a_facturacion(motivo: str) -> str:
    """Consulta financiera; no crea pagos ni acredita aceptación o pago recibido."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return f"TRANSFERIR_FACTURACION: {motivo.strip()}"


@tool
def transferir_a_soporte(motivo: str) -> str:
    """Solicita atención administrativa sin confirmar un pago ni emitir factura."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return _support.invoke({"motivo": motivo.strip()})


@tool
def transferir_a_ventas(motivo: str) -> str:
    """Devuelve una propuesta pendiente o incompatible a Ventas."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo obligatorio")
    return _sales.invoke({"motivo": motivo.strip()})


@tool
def consultar_capacidades_financieras() -> dict:
    """Informa integraciones financieras habilitadas, sin ejecutar operaciones."""
    return {"payment_write_enabled": False, "fiscal_integration_available": False,
            "payment_reconciliation_available": False, "refund_write_enabled": False}


get_financial_capabilities = StructuredTool.from_function(
    func=consultar_capacidades_financieras.func,
    name="get_financial_capabilities",
    description=consultar_capacidades_financieras.description,
    args_schema=consultar_capacidades_financieras.args_schema,
)
