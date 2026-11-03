"""Continuidad sobre el grafo real con agentes simulados, sin Groq, RAG ni BD."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized.conversation import Conversation

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def graph(monkeypatch):
    from app.agents.decentralized.tools.soporte_tools import transferir_a_soporte
    from app.agents.decentralized.tools.tecnico_tools import transferir_a_ventas

    @tool
    def transferir_a_tecnico(motivo: str) -> str:
        """Transferencia simulada a Técnico."""
        return "Transferencia técnica"

    @tool
    def salida_almacen(motivo: str) -> str:
        """Transferencia simulada de Almacén a Ventas."""
        return "Transferencia comercial"

    salida_almacen.name = "transferir_a_ventas"

    @tool
    def consultar_inventario(nombre_repuesto: str, cantidad: int) -> str:
        """Catálogo aislado: SSD de prueba, precio de demostración PEN 180.00."""
        return json.dumps({"requested_name": nombre_repuesto, "name": nombre_repuesto,
                           "quantity": cantidad, "stock": 1, "unit_price": "180.00", "available": True})

    def soporte(state):
        if isinstance(state["messages"][-1], ToolMessage) and state["messages"][-1].name == "transferir_a_soporte":
            return {"current_agent": "soporte", "messages": [AIMessage(content="No puedo registrar citas desde este chat.")]}
        return {"current_agent": "soporte", "messages": [AIMessage(content="", tool_calls=[
            {"name": "transferir_a_tecnico", "args": {"motivo": "Falla"}, "id": "soporte-1"}
        ])]}

    def tecnico(state):
        last = state["messages"][-1]
        user = next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))
        if "revision-solo-servicio" in user:
            reply = AIMessage(content="", tool_calls=[
                {"name": "transferir_a_ventas", "args": {"motivo": "Revisión", "alcance": "solo_servicio"}, "id": "revision"}
            ])
        elif "SSD" in user:
            reply = AIMessage(content="", tool_calls=[
                {"name": "transferir_a_ventas", "args": {
                    "motivo": "Reemplazo de SSD", "alcance": "repuestos",
                    "nombre_repuesto": "SSD de prueba" if "exacto" in user else "", "cantidad": 1,
                }, "id": "cotizar-ssd"}
            ])
        elif isinstance(last, HumanMessage) and "presencial" in last.content:
            reply = AIMessage(content="", tool_calls=[
                {"name": "transferir_a_soporte", "args": {"motivo": "Orientación presencial"}, "id": "tecnico-soporte"}
            ])
        elif isinstance(last, ToolMessage):
            reply = AIMessage(content="¿Qué marca es y qué indicadores se encienden?")
        else:
            assert any("indicadores" in m.content for m in state["messages"] if isinstance(m, AIMessage))
            reply = AIMessage(content="", tool_calls=[
                {"name": "transferir_a_ventas", "args": {"motivo": "Consulta de precio", "alcance": "solo_servicio"}, "id": "tecnico-2"}
            ])
        return {"current_agent": "tecnico", "messages": [reply]}

    def ventas(state):
        if state.get("quote_scope") == "solo_servicio":
            return {"current_agent": "ventas", "messages": [AIMessage(content="Tarifa de revisión pendiente.")]}
        if state.get("required_parts"):
            assert state["inventory_pending"] is False
            assert state["inventory_results"][0]["unit_price"] == "180.00"
            return {"current_agent": "ventas", "messages": [AIMessage(content="Repuesto verificado; mano de obra pendiente.")]}
        assert any("Lenovo" in m.content for m in state["messages"] if isinstance(m, HumanMessage))
        return {"current_agent": "ventas", "messages": [AIMessage(content="Necesito confirmar el servicio antes de cotizar.")]}

    def almacen(state):
        last = state["messages"][-1]
        if isinstance(last, ToolMessage) and last.name == "consultar_inventario":
            call = {"name": "transferir_a_ventas", "args": {"motivo": "Inventario verificado"}, "id": "almacen-ventas"}
        else:
            part = state["required_parts"][0]
            call = {"name": "consultar_inventario", "args": {
                "nombre_repuesto": part["name"], "cantidad": part["quantity"]}, "id": "inventario-ssd"}
        return {"current_agent": "almacen", "messages": [AIMessage(content="", tool_calls=[call])]}

    # Sustituir módulos antes de importar el grafo evita construir clientes reales.
    for name, node, tools in (
        ("soporte", soporte, [transferir_a_tecnico]),
        ("tecnico", tecnico, [transferir_a_ventas, transferir_a_soporte]),
        ("ventas", ventas, []),
        ("almacen", almacen, [consultar_inventario, salida_almacen]),
    ):
        fullname = f"app.agents.decentralized.{name}"
        module = ModuleType(fullname)
        setattr(module, f"{name}_node", node)
        setattr(module, f"{name}_tools", tools)
        monkeypatch.setitem(sys.modules, fullname, module)
    spec = importlib.util.spec_from_file_location("isolated_conversation_graph", ROOT / "app/agents/decentralized/graph.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_graph(checkpointer=MemorySaver())


def test_continua_tecnico_y_luego_ventas_sin_reiniciar_soporte(graph):
    conversation = Conversation(graph)
    first = conversation.send("Mi computadora no enciende")
    assert first["current_agent"] == "tecnico"
    assert first["handoff_history"] == [{"origen": "soporte", "destino": "tecnico"}]
    second = conversation.send("Es Lenovo, sin luces. ¿Qué revisión necesita y cuánto cuesta?")
    assert second["current_agent"] == "ventas"
    assert second["handoff_history"] == [{"origen": "tecnico", "destino": "ventas"}]
    assert len([m for m in second["messages"] if isinstance(m, HumanMessage)]) == 2
    assert second["turn_start_index"] == len(first["messages"])
    assert second["tool_iterations"] == {"tecnico": 1}
    third = conversation.send("¿Qué datos faltan?")
    assert third["current_agent"] == "ventas"
    assert third["handoff_count"] == 0
    assert third["tool_iterations"] == {}


def test_conversaciones_independientes_y_resultado_no_mutable(graph):
    a, b = Conversation(graph), Conversation(graph)
    result = a.send("Mi PC no enciende")
    result["messages"].clear()
    other = b.send("Otro equipo no enciende")
    assert len([m for m in other["messages"] if isinstance(m, HumanMessage)]) == 1
    assert a.send("Es Lenovo")["current_agent"] == "ventas"


def test_solicitud_nueva_descarta_inventario_y_diagnostico():
    class Graph:
        def __init__(self):
            self.inputs = []

        def invoke(self, state, config):
            self.inputs.append(state)
            return {**state, "current_agent": "tecnico", "required_parts": [{"name": "SSD"}],
                    "inventory_results": [{"stock": 1}]}

    graph = Graph()
    conversation = Conversation(graph)
    conversation.send("Primer equipo")
    conversation.send("Continuación")
    assert graph.inputs[-1]["required_parts"] == [{"name": "SSD"}]
    conversation.send("Otro equipo", new_request=True)
    state = graph.inputs[-1]
    assert "required_parts" not in state and "inventory_results" not in state
    assert "current_agent" not in state
    assert len(state["messages"]) == 1


def test_conversation_reuses_checkpoint_thread_until_new_request():
    class Graph:
        def __init__(self):
            self.configs = []

        def invoke(self, state, config):
            self.configs.append(config)
            return {**state, "messages": state["messages"]}

    graph = Graph()
    conversation = Conversation(graph)

    conversation.send("Primera consulta")
    conversation.send("Continuación")
    first_thread = graph.configs[0]["configurable"]["thread_id"]
    assert graph.configs[1]["configurable"]["thread_id"] == first_thread

    conversation.send("Consulta independiente", new_request=True)
    assert graph.configs[2]["configurable"]["thread_id"] != first_thread


def test_turno_fallido_no_guarda_mensaje_y_vacio_no_invoca():
    class Graph:
        def invoke(self, state, config):
            assert len(state["messages"]) == 1
            raise RuntimeError("Fallo simulado")

    conversation = Conversation(Graph())
    with pytest.raises(ValueError):
        conversation.send(" ")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            conversation.send("Consulta")


def isolated_function(filename, name, namespace):
    # Ejecutar solo la función examinada, sin imports/configuración de clientes.
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), filename, "exec"), namespace)
    return namespace[name]


def test_ventas_conserva_preguntas_para_respuestas_breves():
    build = isolated_function("app/agents/decentralized/ventas.py", "construir_contexto_ventas", {
        "AgentState": dict, "AIMessage": AIMessage, "HumanMessage": HumanMessage, "ToolMessage": ToolMessage,
    })
    messages = [AIMessage(content="¿Quieres cotizar mantenimiento?"), HumanMessage(content="Sí, ese")]
    assert build({"messages": messages}) == messages


def test_rag_tecnico_se_repite_en_otro_turno_y_reintenta_errores():
    class Model:
        def __init__(self):
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            return AIMessage(content="Respuesta simulada")

    rag, regular = Model(), Model()
    from app.agents.decentralized.policy import es_revision_comercial, ultimo_usuario, handoff, no_puede_probar, es_atencion
    node = isolated_function("app/agents/decentralized/tecnico.py", "tecnico_node", {
        "AgentState": dict, "AIMessage": AIMessage, "SystemMessage": SystemMessage,
        "ToolMessage": ToolMessage, "SYSTEM_PROMPT": "Técnico", "tecnico_llm_rag": rag, "tecnico_llm": regular,
        "es_revision_comercial": es_revision_comercial, "ultimo_usuario": ultimo_usuario, "handoff": handoff,
        "no_puede_probar": no_puede_probar, "es_atencion": es_atencion,
    })
    previous = ToolMessage(content="Documento anterior", name="consultar_base_conocimiento", tool_call_id="old")
    user = HumanMessage(content="Consulta documentación")
    node({"messages": [previous, user], "turn_start_index": 1})
    success = ToolMessage(content="Documento actual", name="consultar_base_conocimiento", tool_call_id="new")
    node({"messages": [previous, user, success], "turn_start_index": 1})
    error = ToolMessage(content="Error controlado", name="consultar_base_conocimiento", tool_call_id="failed", status="error")
    node({"messages": [previous, user, error], "turn_start_index": 1})
    assert rag.calls == 2 and regular.calls == 1


def test_tecnico_devuelve_atencion_a_soporte_sin_bucle(graph):
    conversation = Conversation(graph)
    conversation.send("Mi laptop no prende")
    result = conversation.send("Quiero información para revisión presencial")
    assert result["current_agent"] == "soporte"
    assert result["handoff_history"] == [{"origen": "tecnico", "destino": "soporte"}]
    assert result["messages"][-1].content == "No puedo registrar citas desde este chat."


def test_diagnostico_local_excluye_textos_de_error(capsys):
    from probar_chat import mostrar_diagnostico

    mostrar_diagnostico({
        "handoff_history": [{"origen": "soporte", "destino": "tecnico"}],
        "errors": ["Error en el agente Técnico: BadRequestError", "texto-privado-de-excepcion"],
    })
    output = capsys.readouterr().out
    assert "soporte → tecnico" in output
    assert "BadRequestError" in output
    assert "texto-privado" not in output


def test_reemplazo_sin_modelo_no_salta_a_ventas(graph):
    conversation = Conversation(graph)
    result = conversation.send("Mi laptop necesita reemplazar el SSD y quiero cotizar")
    assert result["current_agent"] == "tecnico"
    assert result["handoff_history"] == [{"origen": "soporte", "destino": "tecnico"}]
    assert "modelo exacto" in result["messages"][-1].content
    assert not result.get("inventory_results")


def test_reemplazo_identificado_recorre_los_cuatro_agentes(graph):
    conversation = Conversation(graph)
    conversation.send("Necesito reemplazar el SSD y cotizar")
    result = conversation.send("El modelo exacto es SSD de prueba, una unidad")
    assert result["current_agent"] == "ventas"
    assert result["handoff_history"] == [
        {"origen": "tecnico", "destino": "almacen"},
        {"origen": "almacen", "destino": "ventas"},
    ]
    assert result["inventory_pending"] is False
    assert result["required_parts"] == [{"name": "SSD de prueba", "quantity": 1}]


def test_revision_permitida_aunque_inventario_siga_pendiente(graph):
    result = graph.invoke({
        "messages": [HumanMessage(content="revision-solo-servicio")],
        "current_agent": "tecnico", "inventory_pending": True,
    }, config={"configurable": {"thread_id": "revision-pendiente"}})
    assert result["current_agent"] == "ventas"
    assert result["quote_scope"] == "solo_servicio"
    assert result["inventory_pending"] is True
