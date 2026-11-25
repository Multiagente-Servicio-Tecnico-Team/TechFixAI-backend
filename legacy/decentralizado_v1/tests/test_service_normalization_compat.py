import unicodedata

import pytest

from app.agents.decentralized.tools.ventas_tools import normalize_service, normalizar_servicio


@pytest.mark.parametrize("function", [normalize_service, normalizar_servicio])
@pytest.mark.parametrize("style", ["positional", "service", "servicio"])
@pytest.mark.parametrize("value", ["  DIAGNÓSTICO  ", "Instalación", "", "  ", "Otro servicio"])
def test_entry_points_preserve_original_normalization(function, style, value):
    expected = "".join(character for character in unicodedata.normalize("NFD", value.lower().strip())
                       if unicodedata.category(character) != "Mn")
    result = function(value) if style == "positional" else function(**{style: value})
    assert result == expected
    assert normalizar_servicio is normalize_service


@pytest.mark.parametrize("function", [normalize_service, normalizar_servicio])
@pytest.mark.parametrize("value", [None, 2, True, [], b"service"])
def test_invalid_values_keep_original_error(function, value):
    def original(value):
        value = value.lower().strip()
        return "".join(character for character in unicodedata.normalize("NFD", value)
                       if unicodedata.category(character) != "Mn")

    with pytest.raises(Exception) as expected:
        original(value)
    for arguments in ({"service": value}, {"servicio": value}):
        with pytest.raises(type(expected.value)) as actual:
            function(**arguments)
        assert str(actual.value) == str(expected.value)


@pytest.mark.parametrize("function", [normalize_service, normalizar_servicio])
@pytest.mark.parametrize("arguments", [{}, {"unknown": "value"},
    {"service": "same", "servicio": "same"}, {"service": None, "servicio": "value"},
    {"service": "value", "servicio": None}])
def test_missing_unknown_or_duplicate_arguments_are_rejected(function, arguments):
    with pytest.raises(TypeError):
        function(**arguments)


def test_positional_and_legacy_keyword_cannot_select_silently():
    with pytest.raises(TypeError):
        normalize_service("value", servicio="value")
