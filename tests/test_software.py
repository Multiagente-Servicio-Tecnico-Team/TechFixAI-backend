"""Carga el módulo real sustituyendo modelo, dotenv y RAG antes del import."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool


class Model:
    def __init__(self):
        self.response = AIMessage(content="Orientación preliminar; no se ejecutaron cambios.")
        self.calls = []
        self.error = None

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.response


@pytest.fixture
def agent(monkeypatch, request):
    regular, rag = Model(), Model()
    bindings = []

    class FakeGroq:
        def __init__(self, **kwargs):
            if getattr(request, "param", False):
                raise RuntimeError("clave privada de inicialización")
            self.settings = kwargs

        def bind_tools(self, tools, **kwargs):
            bindings.append(([t.name for t in tools], kwargs))
            return rag if kwargs.get("tool_choice") == "required" else regular

    @tool
    def consultar_base_conocimiento(consulta: str) -> str:
        """RAG simulado local."""
        return "Documento simulado"

    for name, attributes in (
        ("langchain_groq", {"ChatGroq": FakeGroq}),
        ("dotenv", {"load_dotenv": lambda: None}),
        ("app.rag.tools", {"consultar_base_conocimiento": consultar_base_conocimiento}),
    ):
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "app/agents/decentralized/software.py"
    spec = importlib.util.spec_from_file_location("isolated_software", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, regular, rag, bindings


def state(text="La aplicación se cierra", **kwargs):
    return {"messages": [HumanMessage(content=text)], **kwargs}


def test_contexto_completo_sin_mutacion_ni_diagnostico_inventado(agent):
    module, regular, _, bindings = agent
    history = [HumanMessage(content="Uso Windows 11"), AIMessage(content="¿Qué aplicación?"),
               HumanMessage(content="El editor se cierra")]
    original = {"messages": history, "ticket_id": 7,
                "technical_assessment": {"hardware_diagnosis": "Pendiente", "software_diagnosis": "Hipótesis previa"}}
    before = deepcopy(original)
    result = module.software_node(original)
    assert original == before
    assert result == {"current_agent": "software", "messages": [regular.response]}
    assert regular.calls[0][2:] == history
    assert "Hipótesis previa" in regular.calls[0][1].content
    assert "Pendiente" in regular.calls[0][1].content
    assert bindings[0][0] == ["transfer_to_support", "transfer_to_hardware", "transfer_to_sales", "consultar_base_conocimiento", "transfer_to_logistics"]


@pytest.mark.parametrize("text", ["Pantalla azul", "Mi equipo está lento"])
def test_ambiguedad_pide_datos(agent, text):
    module, regular, _, _ = agent
    result = module.software_node(state(text))
    assert "sistema operativo" in result["messages"][0].content
    assert not regular.calls


@pytest.mark.parametrize("text", ["Sale humo del equipo", "Tengo batería hinchada", "Quiero reemplazar el SSD"])
def test_evidencia_fisica_transfiere_hardware(agent, text):
    module, regular, _, _ = agent
    call = module.software_node(state(text))["messages"][0].tool_calls[0]
    assert call["name"] == "transfer_to_hardware" and call["args"]["reason"].strip()
    assert not regular.calls


def test_atencion_transfiere_soporte(agent):
    module, _, _, _ = agent
    assert module.software_node(state("Necesito revisión presencial"))["messages"][0].tool_calls[0]["name"] == "transfer_to_support"


def test_rag_por_turno_y_reintento_sin_ejecutar_servicios(agent):
    module, regular, rag, _ = agent
    value = state("Necesito documentación")
    module.software_node(value)
    assert len(rag.calls) == 1 and not regular.calls
    value["messages"].append(ToolMessage(content="Documento simulado", name="consultar_base_conocimiento", tool_call_id="a"))
    module.software_node(value)
    assert len(regular.calls) == 1
    value["messages"].append(HumanMessage(content="Necesito documentación nueva"))
    value["turn_start_index"] = 2
    module.software_node(value)
    assert len(rag.calls) == 2
    value["messages"].append(ToolMessage(content="Fallo simulado", name="consultar_base_conocimiento", tool_call_id="b", status="error"))
    module.software_node(value)
    assert len(rag.calls) == 2
    assert len(regular.calls) == 2


def test_error_no_expone_excepcion_y_conserva_errores(agent):
    module, regular, _, _ = agent
    regular.error = RuntimeError("credencial privada")
    result = module.software_node(state(errors=["Anterior"]))
    assert result["errors"] == ["Anterior", "Error en el agente Software: RuntimeError"]
    assert "credencial" not in str(result)


@pytest.mark.parametrize("changes", [
    {"technical_assessment": {}},
    {"required_parts": [{"name": "SSD", "quantity": 1}]},
    {"requested_items": [{"name": "RAM"}]},
    {"technical_assessment": {"software_diagnosis": "Preliminar", "uncertainties": ["Causa desconocida"]}},
    {"technical_assessment": {"software_diagnosis": "Preliminar", "hardware_diagnosis": "Pendiente"}},
    {"technical_assessment": {"software_diagnosis": "Preliminar", "compatibility_pending": ["SSD"]}},
    {"messages": [HumanMessage(content="¿Cuánto cuesta reparar mi equipo?")]},
])
def test_solo_servicio_no_prueba_ausencia_repuestos(agent, changes):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name="transferir_a_ventas", args={"motivo": "Cotizar", "alcance": "solo_servicio"}, id="a")])
    value = state("Confirmo Servicio definido. Cotiza solo servicio sin repuestos", request_revision=1,
                  technical_assessment={"software_diagnosis": "Servicio definido"})
    value.update(changes)
    result = module.software_node(value)
    assert not result["messages"][0].tool_calls
    assert "definir el servicio" in result["messages"][0].content


def test_servicio_definido_permite_ventas(agent):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name="transferir_a_ventas", args={"motivo": "Servicio de software definido", "alcance": "solo_servicio"}, id="a")])
    result = module.software_node(state("Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos",
                                      request_revision=1, technical_assessment={"software_diagnosis": "Evaluación del editor"}))
    assert result["messages"][0] is regular.response


@pytest.mark.parametrize("name,args", [
    ("ejecutar_instalacion", {}),
    ("transferir_a_tecnico", {"motivo": " "}),
    ("transferir_a_ventas", {"motivo": "Cotizar", "alcance": "repuestos"}),
])
def test_rechaza_llamadas_invalidas_antes_de_ejecutarlas(agent, name, args):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name=name, args=args, id="a")])
    assert not module.software_node(state())["messages"][0].tool_calls


@pytest.mark.parametrize("assessment", [{}, {"backup_confirmed": True}, {"destructive_action_authorized": True}])
def test_reinstalacion_exige_respaldo_y_autorizacion(agent, assessment):
    module, regular, _, _ = agent
    result = module.software_node(state("Quiero reinstalar", technical_assessment=assessment))
    assert "perder información" in result["messages"][0].content
    assert not regular.calls


@pytest.mark.parametrize("calls", [
    [dict(name="transferir_a_soporte", args={"motivo": "Atención"}, id="a"),
     dict(name="transferir_a_tecnico", args={"motivo": "Hardware"}, id="b")],
    [dict(name="transferir_a_tecnico", args={"motivo": "Hardware"}, id="a"),
     dict(name="transferir_a_tecnico", args={"motivo": "Hardware"}, id="b")],
    [dict(name="transferir_a_tecnico", args={"motivo": "Hardware"}, id="a"),
     dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="b")],
    [dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="a"),
     dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="b")],
])
def test_rechaza_lote_completo_sin_llamadas_huerfanas(agent, calls):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=calls)
    result = module.software_node(state())
    assert not result["messages"][0].tool_calls
    assert not result["messages"][0].invalid_tool_calls
    assert "una operación" in result["messages"][0].content
    assert not any(isinstance(message, ToolMessage) for message in result["messages"])


def test_preserva_id_y_argumentos_de_llamada_unica(agent):
    module, regular, _, _ = agent
    call = dict(name="transferir_a_tecnico", args={"motivo": "Revisar evidencia física"}, id="original")
    regular.response = AIMessage(content="", tool_calls=[call])
    assert module.software_node(state())["messages"][0].tool_calls == regular.response.tool_calls


def test_invalid_tool_calls_no_se_devuelven(agent):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", invalid_tool_calls=[dict(name="transferir_a_tecnico", args="{", id="a", error="JSON")])
    assert not module.software_node(state())["messages"][0].invalid_tool_calls


@pytest.mark.parametrize("text", ["No sale humo", "Nunca sale humo", "No tengo batería hinchada",
                                   "No quiero reemplazar el SSD", "Si sale humo, ¿qué hago?"])
def test_negaciones_e_hipotesis_no_son_evidencia_fisica(agent, text):
    module, regular, _, _ = agent
    result = module.software_node(state(text))
    assert not result["messages"][0].tool_calls
    assert len(regular.calls) == 1


def test_peligro_afirmado_prioritario_a_atencion_y_negacion_distinta(agent):
    module, regular, _, _ = agent
    result = module.software_node(state("No tengo batería hinchada, pero sale humo. ¿Cuál es el horario presencial?"))
    assert result["messages"][0].tool_calls[0]["name"] == "transfer_to_hardware"
    assert "suspende las pruebas" in result["messages"][0].content
    assert not regular.calls


@pytest.mark.parametrize("text", ["No sale humo y mi batería está hinchada",
                                   "Tengo batería hinchada y no sale humo"])
def test_negacion_de_otro_sintoma_no_oculta_peligro(agent, text):
    module, regular, _, _ = agent
    assert module.software_node(state(text))["messages"][0].tool_calls[0]["name"] == "transfer_to_hardware"
    assert not regular.calls


@pytest.mark.parametrize("prior", ["Uso Windows 11", "Tengo Ubuntu", "Mi sistema operativo es macOS"])
def test_so_claro_en_historial_no_se_pregunta_otra_vez(agent, prior):
    module, regular, _, _ = agent
    module.software_node({"messages": [HumanMessage(content=prior), HumanMessage(content="Sigue lento")]})
    assert len(regular.calls) == 1


@pytest.mark.parametrize("prior", ["¿Será Windows?", "¿Uso Windows?", "Quizás uso Windows 11", "No uso Windows", "Vi Windows en una tienda"])
def test_mencion_ambigua_no_confirma_so(agent, prior):
    module, regular, _, _ = agent
    result = module.software_node({"messages": [HumanMessage(content=prior), HumanMessage(content="Sigue lento")]})
    assert "sistema operativo" in result["messages"][0].content
    assert not regular.calls


def test_so_en_intake_evitar_pregunta(agent):
    module, regular, _, _ = agent
    module.software_node(state("Pantalla azul", intake={"operating_system": "Windows 11"}))
    assert len(regular.calls) == 1


@pytest.mark.parametrize("diagnosis", ["", " ", "\n\t", None])
def test_diagnostico_vacio_no_define_servicio(agent, diagnosis):
    module, _, _, _ = agent
    assert not module._servicio_definido(state("Confirmo servicio. Cotiza solo servicio",
                                              request_revision=1, technical_assessment={"software_diagnosis": diagnosis}))


@pytest.mark.parametrize("revision", [None, True, -1])
def test_revision_invalida_no_autoriza_ventas(agent, revision):
    module, _, _, _ = agent
    assert not module._servicio_definido(state("Confirmo Servicio definido. Cotiza solo servicio",
                                              request_revision=revision, technical_assessment={"software_diagnosis": "Servicio definido"}))


@pytest.mark.parametrize("text", [
    "Confirmo Servicio definido. No quiero precio ni cotización, solo servicio",
    "No confirmo Servicio definido. Cotiza solo servicio",
    "Cotiza solo servicio sin repuestos",
])
def test_negacion_o_falta_reconfirmacion_actual_bloquea_ventas(agent, text):
    module, _, _, _ = agent
    assert not module._servicio_definido(state(text, request_revision=2,
                                              technical_assessment={"software_diagnosis": "Servicio definido"}))


def test_diagnostico_hardware_historico_no_se_declara_resuelto(agent):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name="transferir_a_ventas", args={"motivo": "Cotizar", "alcance": "solo_servicio"}, id="a")])
    value = state("Confirmo Servicio definido. Cotiza solo servicio", request_revision=2,
                  technical_assessment={"software_diagnosis": "Servicio definido", "hardware_diagnosis": "Hallazgo antiguo"})
    result = module.software_node(value)
    assert "Hardware está resuelto" in result["messages"][0].content
    assert value["technical_assessment"]["hardware_diagnosis"] == "Hallazgo antiguo"


def test_autorizaciones_antiguas_no_se_reutilizan(agent):
    module, regular, _, _ = agent
    value = state("Quiero reinstalar", request_revision=2,
                  technical_assessment={"backup_confirmed": True, "destructive_action_authorized": True})
    result = module.software_node(value)
    assert "vigencia" in result["messages"][0].content and not regular.calls
    value["messages"] = [HumanMessage(content="La aplicación falla")]
    module.software_node(value)
    assert "backup_confirmed" not in regular.calls[0][1].content
    assert value["technical_assessment"]["backup_confirmed"] is True


@pytest.mark.parametrize("status", ["error", "success"])
def test_rag_una_sola_consulta_por_turno_aunque_modelo_la_repita(agent, status):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="b")])
    value = {"messages": [HumanMessage(content="Documentación"), ToolMessage(content="Resultado", name="consultar_base_conocimiento", tool_call_id="a", status=status)]}
    result = module.software_node(value)
    assert not result["messages"][0].tool_calls
    assert "ya se intentó" in result["messages"][0].content


def test_error_modelo_rag_controlado(agent):
    module, _, rag, _ = agent
    rag.error = RuntimeError("datos privados")
    result = module.software_node(state("Documentación"))
    assert result["errors"] == ["Error en el agente Software: RuntimeError"]
    assert "datos privados" not in str(result)


@pytest.mark.parametrize("agent", [True], indirect=True)
def test_error_inicializacion_no_impide_importar(agent):
    module, _, _, _ = agent
    result = module.software_node(state())
    assert result["errors"] == ["Error en el agente Software: RuntimeError"]
    assert "clave privada" not in str(result)


def test_estado_incorrecto_error_controlado(agent):
    module, _, _, _ = agent
    result = module.software_node(state("Sigue lento", intake=None))
    assert result["errors"] == ["Error en el agente Software: AttributeError"]


@pytest.mark.parametrize("style", ["legacy", "mixed"])
@pytest.mark.parametrize("target", ["transferir_a_tecnico", "transferir_a_ventas"])
def test_internal_handoff_view_does_not_rewrite_public_call(agent, monkeypatch, style, target):
    module, regular, _, _ = agent
    args = {"motivo": "Evaluar"}
    if target == "transferir_a_ventas":
        args["alcance"] = "solo_servicio"
    if style == "mixed":
        args["reason"] = "Evaluar"
        if target == "transferir_a_ventas":
            args["scope"] = "solo_servicio"
    regular.response = AIMessage(content="", tool_calls=[dict(name=target, args=args, id="public-call")])
    value = state("Confirmo Servicio definido. Cotiza solo servicio sin repuestos",
                  request_revision=1, technical_assessment={"software_diagnosis": "Servicio definido"})
    original_state, original_response = deepcopy(value), deepcopy(regular.response)
    normalize = module.normalize_handoff_payload
    views = []

    def capture(payload):
        normalized = normalize(payload)
        views.append(normalized)
        return normalized

    monkeypatch.setattr(module, "normalize_handoff_payload", capture)
    result = module.software_node(value)
    assert result["messages"][0] is regular.response
    assert regular.response == original_response and value == original_state
    assert views == [{"reason": "Evaluar", **({"scope": "solo_servicio"} if target == "transferir_a_ventas" else {})}]


@pytest.mark.parametrize("legacy,canonical,left,right", [
    ("accion", "action", "TRANSFERIR_ALMACEN", "SOLICITAR_COTIZACION"),
    ("motivo", "reason", "Evaluar", "private-conflict"),
    ("alcance", "scope", "solo_servicio", "repuestos"),
    ("nombre_repuesto", "part_name", "SSD", None),
    ("cantidad", "quantity", True, 1),
    ("consulta", "query", "SSD", "RAM"),
])
def test_contradictory_internal_aliases_block_the_model_handoff(agent, legacy, canonical, left, right):
    module, regular, _, _ = agent
    args = {"motivo": "Evaluar", legacy: left, canonical: right}
    regular.response = AIMessage(content="", tool_calls=[dict(name="transferir_a_tecnico", args=args, id="blocked")])
    value = state()
    original_state, original_response = deepcopy(value), deepcopy(regular.response)
    result = module.software_node(value)
    assert not result["messages"][0].tool_calls
    assert result["errors"] == ["Error en el agente Software: DataCompatibilityError"]
    assert "private-conflict" not in str(result)
    assert regular.response == original_response and value == original_state


@pytest.mark.parametrize("target,args", [
    ("transferir_a_soporte", {"reason": "Evaluar"}),
    ("transferir_a_tecnico", {"reason": "Evaluar"}),
    ("transferir_a_ventas", {"reason": "Evaluar", "scope": "solo_servicio"}),
    ("consultar_base_conocimiento", {"query": "Documento"}),
])
def test_english_only_live_arguments_keep_public_validation(agent, monkeypatch, target, args):
    module, regular, _, _ = agent

    def forbidden(payload):
        pytest.fail("Public argument validation must precede internal normalization")

    monkeypatch.setattr(module, "normalize_handoff_payload", forbidden)
    regular.response = AIMessage(content="", tool_calls=[dict(name=target, args=args, id="invalid-public")])
    before = deepcopy(regular.response)
    result = module.software_node(state())
    assert not result["messages"][0].tool_calls
    assert result["errors"] == ["Error en el agente Software: ValidationError"]
    assert regular.response == before


@pytest.mark.parametrize("second", ["transferir_a_tecnico", "transferir_a_soporte", "consultar_base_conocimiento"])
def test_multiple_calls_are_rejected_before_normalizing_any_payload(agent, monkeypatch, second):
    module, regular, _, _ = agent

    def forbidden(payload):
        pytest.fail("The complete batch must be rejected before reading a handoff")

    monkeypatch.setattr(module, "normalize_handoff_payload", forbidden)
    args = {"motivo": "Evaluar", "reason": "Evaluar"}
    regular.response = AIMessage(content="", tool_calls=[
        dict(name="transferir_a_tecnico", args=args, id="first"),
        dict(name=second, args={"consulta": "Documento"} if second == "consultar_base_conocimiento" else args,
             id="second"),
    ])
    before = deepcopy(regular.response)
    result = module.software_node(state())
    assert not result["messages"][0].tool_calls and "errors" not in result
    assert "Solo puedo proponer" in result["messages"][0].content
    assert regular.response == before


def test_rag_arguments_stay_outside_handoff_normalization(agent, monkeypatch):
    module, regular, _, _ = agent

    def forbidden(payload):
        pytest.fail("RAG uses its own public schema")

    monkeypatch.setattr(module, "normalize_handoff_payload", forbidden)
    regular.response = AIMessage(content="", tool_calls=[
        dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="rag-public"),
    ])
    before = deepcopy(regular.response)
    assert module.software_node(state())["messages"][0] is regular.response
    assert regular.response == before
