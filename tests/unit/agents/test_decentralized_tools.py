import pytest

from app.agents.decentralized.tools.soporte_tools import (
    consultar_estado_ticket,
    transferir_a_tecnico as soporte_a_tecnico,
    transferir_a_ventas as soporte_a_ventas,
)

from app.agents.decentralized.tools.tecnico_tools import (
    diagnosticar_problema,
    transferir_a_ventas as tecnico_a_ventas,
)

from app.agents.decentralized.tools.ventas_tools import (
    generar_cotizacion,
    transferir_a_tecnico as ventas_a_tecnico,
)


# PRUEBA 1: TICKETS EXISTENTES
@pytest.mark.parametrize(
    "numero, estado",
    [
        (1001, "En revisión"),
        (1002, "Derivado al área técnica"),
        (1003, "Resuelto"),
    ],
)
def test_ticket_existente(numero, estado):
    resultado = consultar_estado_ticket.invoke(
        {"numero_ticket": numero}
    )
    assert estado in resultado


# PRUEBA 2: TICKET INEXISTENTE
def test_ticket_inexistente():
    resultado = consultar_estado_ticket.invoke(
        {"numero_ticket": 9999}
    )
    assert "No se encontró" in resultado


# PRUEBA 3: DIAGNÓSTICOS CONOCIDOS
@pytest.mark.parametrize(
    "sintoma, esperado",
    [
        ("Mi PC no enciende", "fuente"),
        ("Mi PC se apaga", "temperatura"),
        ("Tengo pantalla azul", "memoria RAM"),
        ("Mi equipo esta lento", "recursos"),
    ],
)
def test_diagnosticos(sintoma, esperado):
    resultado = diagnosticar_problema.invoke(
        {"sintoma": sintoma}
    )
    assert esperado.lower() in resultado.lower()


# PRUEBA 4: DIAGNÓSTICO DESCONOCIDO
def test_diagnostico_desconocido():
    resultado = diagnosticar_problema.invoke(
        {"sintoma": "Problema desconocido"}
    )
    assert "No se encontró" in resultado


# PRUEBA 5: NORMALIZACIÓN
def test_diagnostico_normalizacion():
    resultado = diagnosticar_problema.invoke(
        {"sintoma": "  MI PC NO ENCIENDE  "}
    )
    assert "fuente" in resultado.lower()


# PRUEBA 6: SERVICIOS SIN TARIFA VERIFICADA
@pytest.mark.parametrize(
    "servicio",
    [
        "diagnóstico",
        "mantenimiento",
        "reparación",
        "instalación",
    ],
)
def test_cotizaciones(servicio):
    resultado = generar_cotizacion.invoke(
        {"servicio": servicio}
    )

    assert "Tarifa de mano de obra pendiente" in resultado
    assert "No se puede confirmar un precio total" in resultado
    assert "S/" not in resultado


# PRUEBA 7: SERVICIO DESCONOCIDO
def test_cotizacion_desconocida():
    resultado = generar_cotizacion.invoke(
        {"servicio": "Servicio desconocido"}
    )

    assert "No se encontro" in resultado
    assert "S/" not in resultado


# PRUEBA 8: NORMALIZACION
def test_cotizacion_normalizacion():
    resultado = generar_cotizacion.invoke(
        {"servicio": "  REPARACIÓN  "}
    )

    assert "Servicio: reparacion" in resultado
    assert "Tarifa de mano de obra pendiente" in resultado
    assert "S/" not in resultado


# PRUEBA 9: HANDOFFS DE SOPORTE
def test_handoffs_soporte():
    tecnico = soporte_a_tecnico.invoke(
        {"motivo": "Falla de hardware"}
    )
    ventas = soporte_a_ventas.invoke(
        {"motivo": "Solicita precio"}
    )

    assert tecnico == "TRANSFERIR_TECNICO: Falla de hardware"
    assert ventas == "TRANSFERIR_VENTAS: Solicita precio"


# PRUEBA 10: HANDOFFS DE TÉCNICO Y VENTAS
def test_handoffs_otros_agentes():
    ventas = tecnico_a_ventas.invoke(
        {"motivo": "Necesita cotización", "alcance": "solo_servicio"}
    )
    tecnico = ventas_a_tecnico.invoke(
        {"motivo": "Necesita diagnóstico"}
    )

    assert ventas == {
        "accion": "SOLICITAR_COTIZACION",
        "motivo": "Necesita cotización",
        "alcance": "solo_servicio",
        "nombre_repuesto": "",
        "cantidad": 1,
    }
    assert tecnico == "TRANSFERIR_TECNICO: Necesita diagnóstico"
