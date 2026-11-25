"""Decisión explícita sobre una cotización: aceptar reserva stock, así que la duda nunca cuenta como aceptación."""
import pytest

from app.application.quotes import interpret_quote_decision


@pytest.mark.parametrize("message", [
    "sí, acepto", "acepto", "dale", "de acuerdo, procede", "Sí, acepto esta versión", "ok",
])
def test_explicit_acceptance(message):
    assert interpret_quote_decision(message) == "ACCEPT"


@pytest.mark.parametrize("message", ["no acepto", "mejor no", "cancela la cotización"])
def test_explicit_refusal(message):
    assert interpret_quote_decision(message) == "REJECT"


@pytest.mark.parametrize("message", [
    "puedo revisar antes de aceptar",
    "quiero revisarla primero",
    "déjame verla antes de confirmar",
    "antes de pagar quiero ver el detalle",
    "no sé si acepto",
])
def test_deferral_or_doubt_is_not_a_decision(message):
    assert interpret_quote_decision(message) is None
