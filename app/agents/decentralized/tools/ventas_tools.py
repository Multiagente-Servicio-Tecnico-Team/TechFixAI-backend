import unicodedata
from langchain_core.tools import tool


@tool
def solicitar_inventario(consulta: str) -> dict:
    """Deriva a Almacén una consulta comercial de disponibilidad, sin inventar repuestos."""
    return {"accion": "CONSULTAR_DISPONIBILIDAD", "consulta": consulta}


def normalize_service(servicio: str) -> str:
    servicio = servicio.lower().strip()

    return "".join(
        character
        for character in unicodedata.normalize("NFD", servicio)
        if unicodedata.category(character) != "Mn"
    )


@tool
def generar_cotizacion(servicio: str) -> str:
    """
    Identifica el servicio solicitado sin inventar tarifas.

    Los precios de repuestos deben provenir de PostgreSQL.
    La mano de obra requiere una tarifa verificada.
    """

    normalized_service = normalize_service(servicio)

    services = (
        "diagnostico",
        "mantenimiento",
        "reparacion",
        "instalacion",
    )

    for known_service in services:
        if known_service in normalized_service:
            return (
                f"Servicio: {known_service}. "
                "Tarifa de mano de obra pendiente de validacion. "
                "No se puede confirmar un precio total."
            )

    return (
        "No se encontro una cotizacion para el servicio solicitado. "
        "Se requiere evaluacion comercial."
    )


@tool
def transferir_a_tecnico(motivo: str) -> str:
    """
    Transfiere una solicitud al agente Tecnico cuando
    requiere diagnostico especializado.
    """

    return f"TRANSFERIR_TECNICO: {motivo}"

normalizar_servicio = normalize_service
