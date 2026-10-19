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

from app.agents.decentralized.conversation import Conversation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def graph_module(monkeypatch):
    from app.agents.decentralized.tools.soporte_tools import transferir_a_soporte
    from app.agents.decentralized.tools.tecnico_tools import transferir_a_ventas
    from app.agents.decentralized.tools import software_tools as software_transfers

    @tool
    def consultar_base_conocimiento(consulta: str) -> str:
        """Documentación local simulada, sin recuperador real."""
        if consulta == "error":
            raise RuntimeError("Fallo documental simulado")
        return "Documento local simulado"

    def software(state):
        last = state["messages"][-1]
        if isinstance(last, ToolMessage):
            return {"current_agent": "software", "messages": [AIMessage(content="Resultado recibido; orientación de software.")]}
        user = last.content
        call = None
        if user == "documentacion" or user == "error documental":
            call = dict(name="consultar_base_conocimiento", args={"consulta": "error" if user == "error documental" else "consulta"}, id="software-rag")
        elif user == "Confirmo Servicio definido. Cotiza solo servicio":
            call = dict(name="transferir_a_ventas", args={"motivo": "Servicio definido", "alcance": "solo_servicio"}, id="software-ventas")
        elif user == "atencion":
            call = dict(name="transferir_a_soporte", args={"motivo": "Atención general"}, id="software-soporte")
        elif user == "hardware":
            call = dict(name="transferir_a_tecnico", args={"motivo": "Indicio físico"}, id="software-tecnico")
        return {"current_agent": "software", "messages": [AIMessage(content="" if call else "Orientación de software.", tool_calls=[call] if call else [])]}

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
                           "quantity": cantidad, "stock": 1, "unit_price": "180.00", "available": True, "found": True})

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
        ("software", software, [software_transfers.transferir_a_soporte,
                                software_transfers.transferir_a_tecnico,
                                software_transfers.transferir_a_ventas, consultar_base_conocimiento]),
    ):
        fullname = f"app.agents.decentralized.{name}"
        module = ModuleType(fullname)
        setattr(module, f"{name}_node", node)
        setattr(module, f"{name}_tools", tools)
        monkeypatch.setitem(sys.modules, fullname, module)
    spec = importlib.util.spec_from_file_location("isolated_conversation_graph", ROOT / "app/agents/decentralized/graph.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def graph(graph_module):
    return graph_module.graph


def test_importacion_y_fabrica_sin_checkpointer(graph_module):
    assert graph_module.graph.checkpointer is None
    first = graph_module.build_graph()
    second = graph_module.build_graph()
    assert first is not second
    result = first.invoke({"messages": [HumanMessage(content="Mi PC no enciende")]})
    assert result["current_agent"] == "tecnico"
    assert set(graph_module.AGENT_NODES) == {"soporte", "tecnico", "ventas", "almacen", "software", "compras", "facturacion", "logistica", "garantia"}
    assert {"software", "software_tools", "auditar_software"} <= set(first.nodes)
    assert {"facturacion", "facturacion_tools", "auditar_facturacion"}.issubset(first.nodes)
    assert {"logistica", "logistica_tools", "auditar_logistica"}.issubset(first.nodes)
    assert {"garantia", "garantia_tools", "auditar_garantia"}.issubset(first.nodes)


@pytest.mark.parametrize("origin,target,reason,error", [
    ("soporte", "garantia", "Derivar", "no disponible"),
    ("soporte", "almacen", "Derivar", "no permitida"),
    ("ventas", "ventas", "Derivar", "mismo agente"),
    ("soporte", "ventas", "", "Motivo"),
])
def test_auditoria_rechaza_handoffs_invalidos(graph_module, origin, target, reason, error, monkeypatch):
    if error == "no disponible":
        monkeypatch.delitem(graph_module.AGENT_NODES, target)
    state = {"messages": [AIMessage(content="", tool_calls=[{
        "name": f"transferir_a_{target}", "args": {"motivo": reason}, "id": "call"}]),
        ToolMessage(content="Transferencia", name=f"transferir_a_{target}", tool_call_id="call")]}
    result = graph_module.registrar_handoff(state, origin)
    assert result["next_agent"] == "finalizar"
    assert error in result["errors"][-1]
    assert not result.get("handoff_history")


def test_registro_estructurado_y_repeticion_en_auditoria(graph_module):
    state = {"messages": [ToolMessage(content="TRANSFERIR_TECNICO: Compatibilidad",
                                       name="transferir_a_tecnico", tool_call_id="a")],
             "request_revision": 2}
    first = graph_module.registrar_handoff(state, "ventas")
    assert first["handoff_history"] == [{"origin": "ventas", "destination": "tecnico"}]
    assert first["handoff_records"][0]["reason"] == "Compatibilidad"
    assert first["handoff_records"][0]["request_revision"] == 2
    repeated = graph_module.registrar_handoff({**state, **first}, "ventas")
    assert repeated["next_agent"] == "finalizar"
    assert "repetida" in repeated["errors"][-1]
    assert graph_module.preparar_turno({**state, **first})["handoff_records"] == []


def test_checkpointer_continuidad_aislamiento_y_controles(graph_module):
    from langgraph.checkpoint.memory import MemorySaver

    graph = graph_module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "cliente-a"}, "recursion_limit": 100}
    first = graph.invoke({"messages": [HumanMessage(content="Mi PC no enciende")]}, config)
    # Simula controles agotados del turno anterior, recuperados desde memoria.
    graph.update_state(config, {"handoff_count": 5, "tool_iterations": {"tecnico": 6},
                                "errors": ["Error anterior"], "next_agent": "finalizar"})
    second = graph.invoke({"messages": [HumanMessage(content="Es Lenovo") ]}, config)
    assert second["current_agent"] == "ventas"
    assert second["turn_start_index"] == len(first["messages"])
    assert second["handoff_count"] == 1
    assert second["tool_iterations"] == {"tecnico": 1}
    assert second["errors"] == []
    assert len([m for m in second["messages"] if isinstance(m, HumanMessage)]) == 2
    other = graph.invoke({"messages": [HumanMessage(content="Otro equipo")]},
                         {"configurable": {"thread_id": "cliente-b"}})
    assert other["current_agent"] == "tecnico"
    assert len([m for m in other["messages"] if isinstance(m, HumanMessage)]) == 1


def test_fabrica_de_api_utiliza_checkpointer(graph_module, monkeypatch):
    from langgraph.checkpoint.memory import MemorySaver

    # Ejecuta la fábrica real sin cargar FastAPI ni el resto de los patrones.
    factory = isolated_function("app/main.py", "_build_decentralized_graph", {"Any": object})
    monkeypatch.setitem(sys.modules, "app.agents.decentralized.graph", graph_module)
    # In-memory dependency explicitly injected for this isolated unit test only;
    # production lifespan supplies the PostgreSQL saver, never a fallback.
    checkpointer = MemorySaver()
    with pytest.raises(TypeError):
        factory()
    graph = factory(checkpointer)
    assert graph.checkpointer is checkpointer
    result = graph.invoke({"messages": [HumanMessage(content="Mi PC no enciende")]},
                          {"configurable": {"thread_id": "api-test"}})
    assert result["current_agent"] == "tecnico"


def test_continua_tecnico_y_luego_ventas_sin_reiniciar_soporte(graph):
    conversation = Conversation(graph)
    first = conversation.send("Mi computadora no enciende")
    assert first["current_agent"] == "tecnico"
    assert first["handoff_history"] == [{"origin": "soporte", "destination": "tecnico"}]
    second = conversation.send("Es Lenovo, sin luces. ¿Qué revisión necesita y cuánto cuesta?")
    assert second["current_agent"] == "ventas"
    assert second["handoff_history"] == [{"origin": "tecnico", "destination": "ventas"}]
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


def test_identidad_conservada_en_grafo_real_y_reinicio(graph):
    conversation = Conversation(graph, customer_id=7)
    first = conversation.send("Mi PC no enciende")
    assert first["customer_id"] == 7 and first["current_agent"] == "tecnico"
    second = conversation.send("Es Lenovo")
    assert second["customer_id"] == 7 and second["current_agent"] == "ventas"
    third = conversation.send("Otro equipo no enciende", new_request=True)
    assert third["customer_id"] == 7 and third["current_agent"] == "tecnico"
    assert len([message for message in third["messages"] if isinstance(message, HumanMessage)]) == 1


def isolated_function(filename, name, namespace):
    # Ejecutar solo la función examinada, sin imports/configuración de clientes.
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), filename, "exec"), namespace)
    return namespace[name]


def test_ventas_conserva_preguntas_para_respuestas_breves():
    build = isolated_function("app/agents/decentralized/ventas.py", "build_sales_context", {
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
    from app.agents.decentralized.policy import es_revision_comercial, ultimo_usuario, handoff, no_puede_probar, es_atencion, triaje_soporte, transferencia_sin_progreso, peligro_fisico_reportado
    node = isolated_function("app/agents/decentralized/tecnico.py", "tecnico_node", {
        "AgentState": dict, "AIMessage": AIMessage, "SystemMessage": SystemMessage,
        "ToolMessage": ToolMessage, "SYSTEM_PROMPT": "Técnico", "tecnico_llm_rag": rag, "tecnico_llm": regular,
        "is_diagnostic_pricing_query": es_revision_comercial, "latest_user_message": ultimo_usuario, "handoff": handoff,
        "cannot_perform_checks": no_puede_probar, "is_customer_service_query": es_atencion,
        "classify_support_triage": triaje_soporte, "is_handoff_without_progress": transferencia_sin_progreso, "has_reported_physical_hazard": peligro_fisico_reportado,
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
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "soporte"}]
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
    assert result["handoff_history"] == [{"origin": "soporte", "destination": "tecnico"}]
    assert "modelo exacto" in result["messages"][-1].content
    assert not result.get("inventory_results")


def test_reemplazo_identificado_recorre_los_cuatro_agentes(graph):
    conversation = Conversation(graph)
    conversation.send("Necesito reemplazar el SSD y cotizar")
    result = conversation.send("El modelo exacto es SSD de prueba, una unidad")
    assert result["current_agent"] == "ventas"
    assert result["handoff_history"] == [
        {"origin": "tecnico", "destination": "almacen"},
        {"origin": "almacen", "destination": "ventas"},
    ]
    assert result["inventory_pending"] is False
    assert result["required_parts"] == [{"name": "SSD de prueba", "quantity": 1}]


def test_revision_permitida_aunque_inventario_siga_pendiente(graph):
    result = graph.invoke({
        "messages": [HumanMessage(content="revision-solo-servicio")],
        "current_agent": "tecnico", "inventory_pending": True,
    })
    assert result["current_agent"] == "ventas"
    assert result["quote_scope"] == "solo_servicio"
    assert result["inventory_pending"] is True


def test_lote_usa_mismo_destino_motivo_y_alcance(graph_module):
    messages = [ToolMessage(content='{"motivo":"Primero","alcance":"solo_servicio"}', name="transferir_a_ventas", tool_call_id="a"),
                ToolMessage(content='{"motivo":"Segundo","alcance":"sin_determinar"}', name="transferir_a_ventas", tool_call_id="b")]
    result = graph_module.registrar_handoff({"messages": messages}, "tecnico")
    assert graph_module.detectar_handoff(messages) == "ventas"
    assert result["next_agent"] == "ventas"
    assert result["quote_scope"] == "solo_servicio"
    assert result["handoff_records"][0]["reason"] == "Primero"


def test_lote_ignora_error_y_herramientas_ajenas(graph_module):
    messages = [ToolMessage(content="Fallo", name="transferir_a_tecnico", tool_call_id="a", status="error"),
                ToolMessage(content="TRANSFERIR_VENTAS: Cotizar", name="transferir_a_ventas", tool_call_id="b"),
                ToolMessage(content="Documento", name="consultar_documentacion", tool_call_id="c")]
    assert graph_module.detectar_handoff(messages) == "ventas"
    result = graph_module.registrar_handoff({"messages": messages}, "soporte")
    assert result["handoff_records"][0]["reason"] == "Cotizar"


@pytest.mark.parametrize("requester", [None, "tecnico", "software"])
def test_retorno_automatico_solicitante_y_disponibilidad(graph_module, requester):
    state = {"messages": [ToolMessage(content="{}", name="consultar_inventario", tool_call_id="inv")],
             "required_parts": [{"name": "SSD", "quantity": 1}], "inventory_pending": False,
             "inventory_results": [{"tool_call_id": "inv", "requested_name": "SSD", "name": "SSD",
                                    "quantity": 1, "stock": 3, "available": True, "found": True}],
             "inventory_revision": 0, "inventory_requested_by": requester}
    result = graph_module.registrar_handoff(state, "almacen")
    assert result["next_agent"] == "ventas"
    assert result["inventory_requested_by"] is None
    assert result["handoff_records"][0]["reason"] == "Entregar inventario verificado"


@pytest.mark.parametrize("name,status", [("consultar_inventario", "error"), ("transferir_a_ventas", "error"), ("otra", "success")])
def test_inventario_antiguo_no_dispara_retorno_automatico(graph_module, name, status):
    state = {"messages": [ToolMessage(content="Fallo", name=name, tool_call_id="nuevo", status=status)],
             "required_parts": [{"name": "SSD", "quantity": 1}], "inventory_pending": False,
             "inventory_results": [{"tool_call_id": "antiguo"}]}
    result = graph_module.registrar_handoff(state, "almacen")
    assert result["next_agent"] == "almacen"
    assert not result.get("handoff_records")


def test_entrada_directa_software_conserva_estado(graph_module):
    original = {"messages": [HumanMessage(content="Aplicación falla")], "current_agent": "software",
                "request_revision": 2, "ticket_id": 9,
                "technical_assessment": {"software_diagnosis": "Preliminar", "hardware_diagnosis": "Anterior"}}
    result = graph_module.graph.invoke(original)
    assert result["current_agent"] == "software"
    assert result["handoff_count"] == 0
    assert result["technical_assessment"] == original["technical_assessment"]
    assert result["ticket_id"] == 9 and result["request_revision"] == 2
    assert graph_module.route_entry({"current_agent": "compras"}) == "compras"


@pytest.mark.parametrize("user,destination", [("atencion", "soporte"), ("hardware", "tecnico"), ("Confirmo Servicio definido. Cotiza solo servicio", "ventas")])
def test_software_ejecuta_herramientas_y_auditoria(graph_module, user, destination):
    result = graph_module.graph.invoke({"messages": [HumanMessage(content=user)], "current_agent": "software",
                                       "request_revision": 1, "technical_assessment": {"software_diagnosis": "Servicio definido"}})
    assert result["current_agent"] == destination
    assert result["handoff_history"] == [{"origin": "software", "destination": destination}]
    assert result["handoff_records"][0]["destination"] == destination
    messages = result["messages"]
    call = next(m.tool_calls[0] for m in messages if isinstance(m, AIMessage) and m.tool_calls)
    output = next(m for m in messages if isinstance(m, ToolMessage))
    assert output.tool_call_id == call["id"] and output.status == "success"
    if destination == "ventas":
        assert result["quote_scope"] == "solo_servicio"


@pytest.mark.parametrize("user,status", [("documentacion", "success"), ("error documental", "error")])
def test_software_rag_toolnode_y_retorno(graph_module, user, status):
    result = graph_module.graph.invoke({"messages": [HumanMessage(content=user)], "current_agent": "software"})
    output = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert output.name == "consultar_base_conocimiento" and output.status == status
    assert result["current_agent"] == "software" and result["handoff_count"] == 0
    assert result["tool_iterations"] == {"software": 1}


@pytest.mark.parametrize("payload,extra", [
    ({"motivo": "Cotizar", "alcance": "repuestos"}, {}),
    ({"motivo": "Cotizar", "alcance": "sin_determinar"}, {}),
    ({"motivo": "Cotizar"}, {}),
    ({"motivo": "Cotizar", "alcance": "solo_servicio"}, {"required_parts": [{"name": "SSD", "quantity": 1}]}),
    ({"motivo": "Cotizar", "alcance": "solo_servicio"}, {"requested_items": [{"name": "RAM"}]}),
])
def test_guardas_software_ventas_no_actualizan_al_rechazar(graph_module, payload, extra):
    value = {"messages": [ToolMessage(content=json.dumps(payload), name="transferir_a_ventas", tool_call_id="a")],
             "quote_scope": "repuestos", **extra}
    result = graph_module.auditar_software(value)
    assert result["next_agent"] == "finalizar"
    assert "quote_scope" not in result and not result.get("handoff_records")
    assert value["quote_scope"] == "repuestos"


def test_software_limites_y_repeticion_conservados(graph_module):
    assert graph_module.MAX_HANDOFFS == 5 and graph_module.MAX_TOOL_ITERATIONS == 6
    value = {"messages": [ToolMessage(content="TRANSFERIR_SOPORTE: Atención", name="transferir_a_soporte", tool_call_id="a")]}
    first = graph_module.auditar_software(value)
    repeated = graph_module.auditar_software({**value, **first})
    assert repeated["next_agent"] == "finalizar" and "repetida" in repeated["errors"][-1]
    for extra in ({"handoff_count": 5}, {"tool_iterations": {"software": 5}}):
        result = graph_module.auditar_software({**value, **extra})
        assert result["next_agent"] == "finalizar" and not result.get("handoff_records")


def test_software_checkpoint_continuidad_aislamiento_y_reset(graph_module):
    from langgraph.checkpoint.memory import MemorySaver
    graph = graph_module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "software-a"}}
    first = graph.invoke({"messages": [HumanMessage(content="Aplicación falla")], "current_agent": "software"}, config)
    graph.update_state(config, {"handoff_count": 5, "handoff_records": [{"origen": "software", "destino": "soporte"}],
                                "tool_iterations": {"software": 6}, "errors": ["Anterior"]})
    second = graph.invoke({"messages": [HumanMessage(content="Continúa fallando")]}, config)
    assert second["current_agent"] == "software"
    assert second["turn_start_index"] == len(first["messages"])
    assert second["handoff_count"] == 0 and second["handoff_records"] == []
    assert second["tool_iterations"] == {} and second["errors"] == []
    other = graph.invoke({"messages": [HumanMessage(content="Otro equipo")], "current_agent": "software"},
                         {"configurable": {"thread_id": "software-b"}})
    assert len([m for m in other["messages"] if isinstance(m, HumanMessage)]) == 1
    assert len([m for m in second["messages"] if isinstance(m, HumanMessage)]) == 2


@pytest.mark.parametrize("text,target", [
    ("La aplicación se cierra", "software"),
    ("El navegador falla", "software"),
    ("Necesito actualizar los drivers", "software"),
    ("Quiero configurar Windows", "software"),
    ("Mi PC no enciende", "tecnico"),
    ("Quiero reemplazar el SSD", "tecnico"),
    ("No sale humo pero quiero configurar Windows", "software"),
    ("Quiero configurar Windows pero sale humo", "tecnico"),
    ("Pantalla azul", None),
    ("Mi equipo está lento", None),
    ("No quiero configurar Windows", None),
    ("Quizás el driver falla", None),
    ("Si mi PC no enciende", None),
])
def test_soporte_triaje_conservador_real(text, target):
    from app.agents.decentralized import policy
    class Forbidden:
        def invoke(self, messages):
            pytest.fail("El triaje local debe resolver este caso")
    node = isolated_function("app/agents/decentralized/soporte.py", "soporte_node", {
        **vars(policy), "AgentState": dict, "AIMessage": AIMessage, "ToolMessage": ToolMessage,
        "SystemMessage": SystemMessage, "SYSTEM_PROMPT": "Soporte", "soporte_llm": Forbidden(),
    })
    result = node({"messages": [HumanMessage(content=text)]})
    calls = result["messages"][0].tool_calls
    if target:
        assert calls[0]["name"] == {"software": "transfer_to_software", "tecnico": "transfer_to_hardware"}[target]
        assert calls[0]["args"]["reason"].strip()
    else:
        assert not calls and "No puedo determinar" in result["messages"][0].content


def test_soporte_historial_respuesta_breve_y_cambio_consulta():
    from app.agents.decentralized.policy import triaje_soporte
    history = [HumanMessage(content="La aplicación se cierra"),
               AIMessage(content="¿Qué aplicación falla?"), HumanMessage(content="El editor")]
    assert triaje_soporte({"messages": history}) == "software"
    assert triaje_soporte({"messages": [*history, HumanMessage(content="¿Qué es Windows?")]}) is None
    assert triaje_soporte({"messages": [*history, HumanMessage(content="No quiero configurar Windows")]}) == "aclarar"


@pytest.mark.parametrize("text,target", [("La aplicación se cierra", "software"), ("Mi PC no enciende", "tecnico")])
def test_soporte_real_integrado_transfiere_y_conserva_contexto(graph_module, text, target):
    from app.agents.decentralized import policy
    from app.agents.decentralized.tools.support_handoff_tools import transfer_to_software, transfer_to_hardware
    node = isolated_function("app/agents/decentralized/soporte.py", "soporte_node", {
        **vars(policy), "AgentState": dict, "AIMessage": AIMessage, "ToolMessage": ToolMessage,
        "SystemMessage": SystemMessage,
    })
    graph_module.AGENT_NODES["soporte"] = node
    graph_module.soporte_tools = [transfer_to_software, transfer_to_hardware]
    graph = graph_module.build_graph()
    result = graph.invoke({"messages": [HumanMessage(content=text)], "ticket_id": 7})
    assert result["current_agent"] == target and result["ticket_id"] == 7
    assert result["handoff_history"] == [{"origin": "soporte", "destination": target}]
    assert result["handoff_records"][0]["destination"] == target
    output = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    call = next(m.tool_calls[0] for m in result["messages"] if isinstance(m, AIMessage) and m.tool_calls)
    assert output.status == "success" and output.tool_call_id == call["id"]
    conversation = Conversation(graph)
    first = conversation.send(text)
    if target == "software":
        second = conversation.send("Uso Windows 11")
        assert second["current_agent"] == "software" and second["handoff_history"] == []
        assert any(isinstance(m, HumanMessage) and m.content == text for m in second["messages"])


def test_soporte_consulta_general_no_reactiva_falla_antigua():
    from app.agents.decentralized import policy
    class Model:
        def invoke(self, messages):
            return AIMessage(content="Consulta general atendida")
    node = isolated_function("app/agents/decentralized/soporte.py", "soporte_node", {
        **vars(policy), "AgentState": dict, "AIMessage": AIMessage, "ToolMessage": ToolMessage,
        "SystemMessage": SystemMessage, "SYSTEM_PROMPT": "Soporte", "soporte_llm": Model(),
    })
    for text in ("Consulta el ticket 7", "¿Qué es Windows?", "¿Cuál es el horario presencial?"):
        result = node({"messages": [HumanMessage(content="Mi PC no enciende"), HumanMessage(content=text)]})
        assert not result["messages"][0].tool_calls


def hardware_node(model=None):
    from app.agents.decentralized import policy
    class Model:
        def invoke(self, messages):
            return AIMessage(content="Evaluación Hardware preliminar")
    return isolated_function("app/agents/decentralized/tecnico.py", "tecnico_node", {
        **vars(policy), "AgentState": dict, "AIMessage": AIMessage, "ToolMessage": ToolMessage,
        "SystemMessage": SystemMessage, "SYSTEM_PROMPT": "Hardware",
        "tecnico_llm": model or Model(), "tecnico_llm_rag": model or Model(),
    })


@pytest.mark.parametrize("text,target", [
    ("La aplicación se cierra", "software"),
    ("Quiero configurar Windows", "software"),
    ("El driver falla", "software"),
    ("La aplicación falla, cotiza un diagnóstico", "software"),
    ("Mi equipo no enciende", None),
    ("La aplicación falla pero mi PC no enciende", None),
    ("Pantalla azul", None),
    ("Mi equipo está lento", None),
    ("No quiero configurar Windows", None),
    ("Quizás el driver falla", None),
    ("No sale humo pero el editor falla", "software"),
    ("No sale humo pero mi PC no enciende", None),
])
def test_tecnico_especializado_triaje(text, target):
    value = {"messages": [HumanMessage(content=text)]}
    result = hardware_node()(value)
    calls = result["messages"][0].tool_calls
    if target:
        assert calls[0]["name"] == "transfer_to_software" and calls[0]["args"]["reason"].strip()
    else:
        assert not calls
    assert "technical_assessment" not in result


def test_peligro_no_se_omite_por_peticion_comercial():
    result = hardware_node()({"messages": [HumanMessage(content="Sale humo, cuánto cuesta el diagnóstico presencial")]})
    assert not result["messages"][0].tool_calls
    assert "suspende las pruebas" in result["messages"][0].content


def test_peligro_negado_no_se_trata_como_reportado():
    result = hardware_node()({"messages": [HumanMessage(content="No sale humo pero mi PC no enciende")]})
    assert result["messages"][0].content == "Evaluación Hardware preliminar"


@pytest.mark.parametrize("extra", [{"required_parts": [{"name": "SSD", "quantity": 1}]},
                                   {"requested_items": [{"name": "RAM"}]},
                                   {"technical_assessment": {"hardware_diagnosis": "Pendiente"}}])
def test_software_no_salta_componentes_o_hallazgos_pendientes(extra):
    value = {"messages": [HumanMessage(content="La aplicación falla, cotiza diagnóstico")], **extra}
    result = hardware_node()(value)
    assert not result["messages"][0].tool_calls
    assert "componentes pendientes" in result["messages"][0].content


def test_tecnico_repeticion_token_y_evidencia_nueva(graph_module):
    value = {"messages": [HumanMessage(content="La aplicación se cierra")], "request_revision": 1}
    first = hardware_node()(value)
    call = first["messages"][0].tool_calls[0]
    value["messages"].extend([first["messages"][0], ToolMessage(content="TRANSFERIR_SOFTWARE: Evaluación", name=call["name"], tool_call_id=call["id"])])
    audited = graph_module.auditar_tecnico(value)
    value.update(audited)
    repeated = hardware_node()(value)
    assert not repeated["messages"][0].tool_calls
    assert "información nueva" in repeated["messages"][0].content
    value["messages"].append(ToolMessage(content="Nueva evidencia documental", name="consultar_base_conocimiento", tool_call_id="doc"))
    assert hardware_node()(value)["messages"][0].tool_calls[0]["name"] == "transfer_to_software"


def test_tecnico_real_software_integracion_y_continuidad(graph_module):
    from app.agents.decentralized.tools.hardware_handoff_tools import transfer_to_software
    graph_module.AGENT_NODES["tecnico"] = hardware_node()
    graph_module.tecnico_tools = [*graph_module.tecnico_tools, transfer_to_software]
    graph = graph_module.build_graph()
    result = graph.invoke({"current_agent": "tecnico", "messages": [HumanMessage(content="La aplicación se cierra")], "ticket_id": 7})
    assert result["current_agent"] == "software" and result["ticket_id"] == 7
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "software"}]
    assert result["handoff_records"][0]["reason"].strip()
    output = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert output.name == "transfer_to_software" and output.status == "success"
    next_turn = graph.invoke({**result, "messages": [*result["messages"], HumanMessage(content="Uso Windows 11")]})
    assert next_turn["current_agent"] == "software" and next_turn["handoff_history"] == []
    back = graph.invoke({"current_agent": "software", "messages": [HumanMessage(content="hardware")]})
    assert back["current_agent"] == "tecnico"
    assert back["handoff_history"] == [{"origin": "software", "destination": "tecnico"}]


@pytest.mark.parametrize("changes", [
    {"request_revision": None}, {"request_revision": True}, {"request_revision": -1},
    {"technical_assessment": {"software_diagnosis": " "}},
    {"technical_assessment": {"software_diagnosis": "Servicio anterior"}},
    {"technical_assessment": {"software_diagnosis": "Servicio definido", "uncertainties": ["Pendiente"]}},
    {"technical_assessment": {"software_diagnosis": "Servicio definido", "compatibility_pending": ["Modelo"]}},
    {"messages": [HumanMessage(content="No confirmo Servicio definido. Cotiza solo servicio")]},
    {"messages": [HumanMessage(content="Confirmo Servicio definido. No quiero cotizar solo servicio")]},
    {"messages": [HumanMessage(content="Confirmo Servicio definido. Cotiza reparación. No solo servicio")]},
    {"messages": [HumanMessage(content="Quizás confirmo Servicio definido. Cotiza solo servicio")]},
    {"required_parts": [{"name": "SSD", "quantity": 1}]},
])
def test_auditoria_comercial_software_comparte_elegibilidad(graph_module, changes):
    value = {"messages": [HumanMessage(content="Confirmo Servicio definido. Cotiza solo servicio")],
             "request_revision": 1, "technical_assessment": {"software_diagnosis": "Servicio definido"}}
    value.update(changes)
    value["messages"] = [*value["messages"], ToolMessage(content='{"motivo":"Evaluar servicio","alcance":"solo_servicio"}',
                                                       name="transferir_a_ventas", tool_call_id="a")]
    result = graph_module.auditar_software(value)
    assert result["next_agent"] == "finalizar"
    assert "quote_scope" not in result and not result.get("handoff_records")


def test_auditoria_comercial_valida_y_ventas_real_tarifa_pendiente(graph_module):
    from app.agents.decentralized import policy
    namespace = {**vars(policy), "AgentState": dict, "AIMessage": AIMessage,
                 "HumanMessage": HumanMessage, "ToolMessage": ToolMessage,
                 "SystemMessage": SystemMessage, "json": json,
                 "SYSTEM_PROMPT": "Ventas", "Decimal": __import__("decimal").Decimal,
                 "InvalidOperation": __import__("decimal").InvalidOperation}
    for name in ("validate_inventory", "build_sales_context", "build_inventory_context", "ventas_node"):
        namespace[name] = isolated_function("app/agents/decentralized/ventas.py", name, namespace)
    # Las funciones extraídas necesitan compartir sus dependencias.
    namespace["ventas_node"].__globals__.update(namespace)
    graph_module.AGENT_NODES["ventas"] = namespace["ventas_node"]
    result = graph_module.build_graph().invoke({
        "messages": [HumanMessage(content="Confirmo Servicio definido. Cotiza solo servicio")],
        "current_agent": "software", "request_revision": 1,
        "technical_assessment": {"software_diagnosis": "Servicio definido"}})
    assert result["current_agent"] == "ventas" and result["quote_scope"] == "solo_servicio"
    assert result["quote"]["total"] is None and result["quote"]["labor_total"] is None
    assert "preliminar" in result["messages"][-1].content
    assert "tarifa" in result["messages"][-1].content.lower()
    assert not result.get("quote_id")


def inventory_fixture(name="SSD de prueba", quantity=1):
    return {"requested_name": name, "name": name, "quantity": quantity, "stock": 3,
            "unit_price": "180.00", "available": quantity <= 3, "found": True, "tool_call_id": "inv"}


@pytest.mark.parametrize("inventory_revision", [None, 1, True])
def test_revision_antigua_o_ausente_no_reutiliza_inventario(inventory_revision):
    from app.agents.decentralized.policy import preparar_inventario
    part = {"name": "SSD de prueba", "quantity": 1}
    update = preparar_inventario({"request_revision": 2, "inventory_revision": inventory_revision,
                                  "inventory_results": [inventory_fixture()], "inventory_requested_by": "software"}, [part])
    assert update["inventory_results"] == [] and update["inventory_pending"] is True
    assert update["inventory_requested_by"] == "ventas"


def test_cambio_cantidad_invalida_solo_coincidencias_afectadas():
    from app.agents.decentralized.policy import preparar_inventario
    values = [inventory_fixture(), inventory_fixture("RAM de prueba")]
    value = {"request_revision": 2, "inventory_revision": 2, "inventory_results": values}
    required = [{"name": "SSD de prueba", "quantity": 2}, {"name": "RAM de prueba", "quantity": 1}]
    update = preparar_inventario(value, required)
    assert update["inventory_results"] == [values[1]] and update["inventory_pending"] is True
    same = preparar_inventario(value, [{"name": "SSD de prueba", "quantity": 1}])
    assert same["inventory_results"] == [values[0]] and same["inventory_pending"] is False
    assert value["inventory_results"] == values


@pytest.mark.parametrize("complete", [False, True])
def test_almacen_real_retorno_y_solicitante_obsoleto(graph_module, complete):
    from app.agents.decentralized.tools.warehouse_handoff_tools import transfer_to_sales
    graph_module.almacen_tools = [*graph_module.almacen_tools, transfer_to_sales]
    from app.agents.decentralized import policy
    from langchain_core.tools import StructuredTool
    legacy = next(item for item in graph_module.almacen_tools if item.name == "consultar_inventario")
    def lookup(part_name: str, quantity: int = 1) -> str:
        return legacy.invoke({"nombre_repuesto": part_name, "cantidad": quantity})
    graph_module.almacen_tools = [*graph_module.almacen_tools, StructuredTool.from_function(
        func=lookup, name="check_inventory", description=legacy.description)]
    node = isolated_function("app/agents/decentralized/almacen.py", "almacen_node", {
        **vars(policy), "AgentState": dict, "AIMessage": AIMessage, "ToolMessage": ToolMessage,
    })
    graph_module.AGENT_NODES["almacen"] = node
    result = graph_module.build_graph().invoke({
        "messages": [HumanMessage(content="Consultar SSD de prueba")], "current_agent": "almacen",
        "required_parts": [{"name": "SSD de prueba", "quantity": 1}], "request_revision": 2,
        "inventory_revision": 2 if complete else 1, "inventory_pending": not complete,
        "inventory_results": [inventory_fixture()], "inventory_requested_by": "software"})
    assert result["current_agent"] == "ventas" and result["inventory_requested_by"] is None
    assert result["inventory_revision"] == 2 and result["inventory_pending"] is False
    assert result["handoff_history"] == [{"origin": "almacen", "destination": "ventas"}]
    queries = [m for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "check_inventory"]
    assert len(queries) == (0 if complete else 1)


def test_guardar_inventario_rechaza_referencia_ajena_y_completa_por_partes(graph_module):
    value = {"request_revision": 2, "inventory_revision": 2,
             "required_parts": [{"name": "SSD de prueba", "quantity": 1}, {"name": "RAM de prueba", "quantity": 1}],
             "inventory_results": [inventory_fixture()],
             "messages": [ToolMessage(content=json.dumps(inventory_fixture("Otro")), name="consultar_inventario", tool_call_id="other")]}
    wrong = graph_module.guardar_inventario(value)
    assert wrong["inventory_pending"] is True and len(wrong["inventory_results"]) == 1
    value["messages"] = [ToolMessage(content=json.dumps(inventory_fixture("RAM de prueba")), name="consultar_inventario", tool_call_id="ram")]
    result = graph_module.guardar_inventario(value)
    assert result["inventory_pending"] is False and result["inventory_revision"] == 2
    assert len(result["inventory_results"]) == 2


def test_entrada_tecnico_almacen_reemplaza_solicitante_y_requerimiento(graph_module):
    value = {"messages": [HumanMessage(content="El técnico indicó SSD de prueba"),
                           ToolMessage(content='{"accion":"TRANSFERIR_ALMACEN","motivo":"Verificar SSD","nombre_repuesto":"SSD de prueba","cantidad":2}', name="transferir_a_almacen", tool_call_id="a")],
             "request_revision": 2, "inventory_revision": 2, "inventory_requested_by": "software",
             "required_parts": [{"name": "SSD de prueba", "quantity": 1}], "inventory_results": [inventory_fixture()]}
    update = graph_module.auditar_tecnico(value)
    assert update["next_agent"] == "almacen" and update["inventory_requested_by"] == "ventas"
    assert update["inventory_results"] == [] and update["required_parts"][0]["quantity"] == 2

    value["required_parts"].append({"name": "RAM de prueba", "quantity": 1})
    value["inventory_results"].append(inventory_fixture("RAM de prueba"))
    partial = graph_module.auditar_tecnico(value)
    assert len(partial["required_parts"]) == 2
    assert partial["inventory_results"] == [inventory_fixture("RAM de prueba")]


def test_fallo_no_acepta_resultados_de_revision_anterior(graph_module):
    result = graph_module.guardar_inventario({
        "request_revision": 2, "inventory_revision": 1, "inventory_results": [inventory_fixture()],
        "required_parts": [{"name": "SSD de prueba", "quantity": 1}],
        "messages": [ToolMessage(content="Fallo", name="consultar_inventario", tool_call_id="a", status="error")]})
    assert result["inventory_results"] == [] and result["inventory_pending"] is True
    assert result["inventory_revision"] is None and result["errors"]
