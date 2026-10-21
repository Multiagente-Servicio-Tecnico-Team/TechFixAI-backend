"""Grafo, nodos y herramientas reales; solo servicios externos sustituidos.

Las respuestas y catálogo son fixtures, no certifican Groq ni PostgreSQL real.
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from app.agents.decentralized.data_compat import normalize_handoff_record

ROOT = Path(__file__).resolve().parents[1]


def call(name, **args):
    return AIMessage(content="", tool_calls=[dict(name=name, args=args, id=uuid4().hex)])


@pytest.fixture
def network(monkeypatch):
    controls = {"handlers": {}, "inventory_calls": [], "rag_calls": []}

    class BoundModel:
        def __init__(self, role, required):
            self.role, self.required = role, required

        def invoke(self, messages):
            handler = controls["handlers"].get(self.role)
            if handler:
                return handler(messages)
            if self.required:
                return call("consultar_base_conocimiento", consulta="Documento de prueba")
            return AIMessage(content="Orientación preliminar simulada; no se ejecutaron cambios.")

    class FakeGroq:
        def __init__(self, **kwargs):
            self.role = None

        def bind_tools(self, tools, **kwargs):
            names = {tool.name for tool in tools}
            if "get_ticket_status" in names:
                self.role = "soporte"
            elif "diagnose_issue" in names:
                self.role = "tecnico"
            elif "identify_quote_service" in names:
                self.role = "ventas"
            elif "check_inventory" in names:
                self.role = "almacen"
            elif "transfer_to_hardware" in names:
                self.role = "software"
            return BoundModel(self.role, kwargs.get("tool_choice") == "required")

    groq = ModuleType("langchain_groq")
    groq.ChatGroq = FakeGroq
    monkeypatch.setitem(sys.modules, "langchain_groq", groq)
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)

    retriever = ModuleType("app.rag.retriever")
    def search(consulta, k):
        controls["rag_calls"].append(consulta)
        return [SimpleNamespace(metadata={"source": "fixture"}, page_content="Documento técnico de prueba")]
    retriever.buscar_conocimiento = search
    monkeypatch.setitem(sys.modules, "app.rag.retriever", retriever)

    from app.database import repository
    def inventory(*, requested_name, quantity):
        controls["inventory_calls"].append((requested_name, quantity))
        if controls.get("inventory_error"):
            raise RuntimeError("Fallo de consulta simulado")
        # Mismo catálogo aislado usado por tests/test_decentralized_repository.py.
        stock = controls.get("inventory_stock", 3)
        return {"requested_name": requested_name, "name": "SSD de prueba", "quantity": quantity,
                "stock": stock, "unit_price": "180.00", "available": quantity <= stock,
                "inventory_id": 1, "found": True}
    monkeypatch.setattr(repository, "lookup_inventory", inventory)

    modules = {}
    for name in ("app.rag.tools", "app.agents.decentralized.tools.almacen_tools",
                 "app.agents.decentralized.soporte", "app.agents.decentralized.tecnico",
                 "app.agents.decentralized.software", "app.agents.decentralized.ventas",
                 "app.agents.decentralized.almacen", "app.agents.decentralized.graph"):
        path = ROOT / (name.replace(".", "/") + ".py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        modules[name.rsplit(".", 1)[-1]] = module
    return modules["graph"], controls


def run(network, text, active=None, **fields):
    module, _ = network
    value = {"messages": [HumanMessage(content=text)], **fields}
    if active:
        value["current_agent"] = active
    result = module.graph.invoke(value, config={"recursion_limit": 100})
    pairs(result)
    return result


def pairs(result):
    calls = {call["id"]: call["name"] for message in result["messages"]
             if isinstance(message, AIMessage) for call in message.tool_calls}
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(outputs) == len(calls)
    assert {message.tool_call_id for message in outputs} == set(calls)
    assert all(calls[message.tool_call_id] == message.name for message in outputs)


def edges(result):
    assert len(result["handoff_records"]) == result["handoff_count"]
    return [(record["origin"], record["destination"])
            for record in map(normalize_handoff_record, result["handoff_records"])]


@pytest.mark.parametrize("text,target", [("La aplicación se cierra", "software"), ("Mi PC no enciende", "tecnico")])
def test_soporte_hacia_especialistas(network, text, target):
    result = run(network, text)
    assert edges(result) == [("soporte", target)]
    assert result["current_agent"] == target


def test_soporte_tecnico_software(network):
    _, controls = network
    controls["handlers"]["tecnico"] = lambda messages: call("transferir_a_software", motivo="Evaluar hipótesis lógica con Software")
    result = run(network, "Mi PC no enciende")
    assert edges(result) == [("soporte", "tecnico"), ("tecnico", "software")]


@pytest.mark.parametrize("text,target", [("Sale humo del equipo", "tecnico"), ("Necesito atención presencial", "soporte")])
def test_software_retorna_a_area_correcta(network, text, target):
    result = run(network, text, "software")
    assert edges(result) == [("software", target)]
    assert not result.get("technical_assessment")


def commercial():
    return {"request_revision": 2, "technical_assessment": {"software_diagnosis": "Evaluación del editor"}}


def test_software_ventas_valido(network):
    _, controls = network
    controls["handlers"]["software"] = lambda messages: call("transferir_a_ventas", motivo="Evaluación del editor", alcance="solo_servicio")
    result = run(network, "Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos", "software", **commercial())
    assert edges(result) == [("software", "ventas")]
    assert result["quote_scope"] == "solo_servicio"
    assert result["quote"]["total"] is None and result["quote"]["labor_total"] is None
    assert "tarifa" in result["messages"][-1].content.lower()
    assert not result.get("quote_id")


@pytest.mark.parametrize("changes,text", [
    ({"technical_assessment": {"software_diagnosis": " "}}, "Confirmo Evaluación del editor. Cotiza solo servicio"),
    ({"request_revision": None}, "Confirmo Evaluación del editor. Cotiza solo servicio"),
    ({}, "No confirmo Evaluación del editor. Cotiza solo servicio"),
])
def test_software_ventas_invalido(network, changes, text):
    _, controls = network
    controls["handlers"]["software"] = lambda messages: call("transferir_a_ventas", motivo="Evaluación del editor", alcance="solo_servicio")
    result = run(network, text, "software", **{**commercial(), **changes})
    assert edges(result) == [] and result["current_agent"] == "software"
    assert not result.get("quote")


@pytest.mark.parametrize("active", ["tecnico", "software"])
def test_reparacion_inventario_ventas(network, active):
    _, controls = network
    controls["handlers"]["tecnico"] = lambda messages: call("transferir_a_almacen", motivo="Verificar pieza indicada", nombre_repuesto="SSD de prueba", cantidad=1)
    result = run(network, "Quiero reemplazar el SSD de prueba", active, request_revision=2, inventory_requested_by="software")
    expected = [("tecnico", "almacen"), ("almacen", "ventas")]
    assert edges(result) == ([("software", "tecnico")] + expected if active == "software" else expected)
    assert result["inventory_requested_by"] is None and result["inventory_revision"] == 2
    assert controls["inventory_calls"] == [("SSD de prueba", 1)]
    assert result["quote"]["known_parts_subtotal"] == "180.00" and result["quote"]["total"] is None


def test_rag_y_checkpoint_multiturno_aislado(network):
    module, controls = network
    graph = module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "software-a"}, "recursion_limit": 100}
    first = graph.invoke({"current_agent": "software", "messages": [HumanMessage(content="Necesito documentación")], "ticket_id": 7}, config)
    second = graph.invoke({"messages": [HumanMessage(content="Continúo la consulta")]}, config)
    pairs(first); pairs(second)
    assert second["current_agent"] == "software" and second["ticket_id"] == 7
    assert len(controls["rag_calls"]) == 1
    assert second["turn_start_index"] == len(first["messages"])
    assert second["messages"][:len(first["messages"])] == first["messages"]
    other = graph.invoke({"current_agent": "software", "messages": [HumanMessage(content="Otra consulta")]},
                         {"configurable": {"thread_id": "software-b"}})
    assert not other.get("ticket_id") and len(other["messages"]) == 2


@pytest.mark.parametrize("revision,complete", [(2, True), (1, True), (2, False)])
def test_inventario_revision_y_parcial(network, revision, complete):
    _, controls = network
    previous = {"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 1,
                "stock": 3, "unit_price": "180.00", "available": True, "found": True, "tool_call_id": "old"}
    result = run(network, "Consultar pieza indicada", "almacen", request_revision=2, inventory_revision=revision,
                 required_parts=[{"name": "SSD de prueba", "quantity": 1}], inventory_results=[previous] if complete else [],
                 inventory_requested_by="software")
    assert edges(result) == [("almacen", "ventas")]
    assert result["inventory_requested_by"] is None and result["inventory_pending"] is False
    assert len(controls["inventory_calls"]) == (0 if complete and revision == 2 else 1)


def test_consulta_fallida_no_cotiza(network):
    _, controls = network
    controls["inventory_error"] = True
    result = run(network, "Consultar pieza indicada", "almacen", request_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 1}])
    assert edges(result) == [] and result["inventory_pending"] is True
    assert not result.get("quote") and result["errors"]


def test_ciclo_sin_progreso_finaliza(network):
    _, controls = network
    controls["handlers"]["tecnico"] = lambda messages: call("transferir_a_software", motivo="Evaluación lógica")
    controls["handlers"]["software"] = lambda messages: call("transferir_a_tecnico", motivo="Revisar Hardware")
    result = run(network, "Mi PC no enciende", "tecnico")
    assert len(edges(result)) == 2
    assert result["next_agent"] == "finalizar" and any("repetida" in error for error in result["errors"])


def test_limite_herramientas_real(network):
    _, controls = network
    controls["handlers"]["tecnico"] = lambda messages: call("diagnosticar_problema", sintoma="Síntoma de prueba sin coincidencia")
    result = run(network, "Mi PC no enciende", "tecnico")
    assert result["tool_iterations"] == {"tecnico": 6}
    assert any("Límite de herramientas" in error for error in result["errors"])


def test_limite_handoffs_con_evidencia_nueva(network):
    _, controls = network
    def hardware(messages):
        count = sum(isinstance(m, ToolMessage) and m.name == "diagnosticar_problema" for m in messages)
        if isinstance(messages[-1], HumanMessage):
            return call("transferir_a_software", motivo="Evaluación inicial")
        if isinstance(messages[-1], ToolMessage) and messages[-1].name == "diagnosticar_problema":
            return call("transferir_a_software", motivo="Nueva evaluación")
        return call("diagnosticar_problema", sintoma="no enciende" if count == 0 else "se apaga")
    controls["handlers"]["tecnico"] = hardware
    controls["handlers"]["software"] = lambda messages: call("transferir_a_tecnico", motivo="Evaluar evidencia nueva")
    result = run(network, "Mi PC no enciende", "tecnico")
    assert result["handoff_count"] == 5
    assert any("Límite de transferencias" in error for error in result["errors"])
