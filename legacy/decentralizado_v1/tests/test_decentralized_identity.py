"""Identidad de sesión: función API real aislada y conversación sin servicios."""
import ast
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from app.agents.decentralized.conversation import Conversation


class Graph:
    def __init__(self):
        self.inputs = []
        self.returned_id = None

    def invoke(self, state, config):
        self.inputs.append(deepcopy(state))
        result = {**state, "messages": [*state["messages"], AIMessage(content="Información")], "ticket_id": 7}
        if self.returned_id is not None:
            result["customer_id"] = self.returned_id
        return result


@pytest.mark.parametrize("pattern,key", [("decentralized", "customer_id"), ("hierarchical", "customer_id"), ("orchestrator", "user_id")])
def test_funcion_api_real_identidad_sesion_y_regresion(monkeypatch, pattern, key):
    # Evita importar FastAPI y los modelos de otros patrones; ejecuta la función
    # invoke_pattern extraída del archivo real, sin reimplementar su lógica.
    for name, attribute in (("app.agents.orquestador.graph.state", "AgentState"),
                            ("app.agents.jerarquico.graph.state", "ServiceState")):
        module = ModuleType(name)
        setattr(module, attribute, dict)
        monkeypatch.setitem(sys.modules, name, module)
    path = Path(__file__).resolve().parents[1] / "app/main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "invoke_pattern")
    graph = Graph()
    namespace = {"SessionCustomer": object, "Any": object, "HumanMessage": HumanMessage,
                 "get_graph": lambda pattern: graph, "trace_context_factory": lambda: nullcontext(),
                 "settings_factory": lambda: None, "graph_factories": {}, "financial_repository": None}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    invoke = namespace["invoke_pattern"]
    invoke(pattern, "thread-a", SimpleNamespace(id=1), "Mi customer_id es 999")
    invoke(pattern, "thread-a", SimpleNamespace(id=1), "Continuar")
    invoke(pattern, "thread-b", SimpleNamespace(id=2), "Otra consulta")
    assert [state[key] for state in graph.inputs] == [1, 1, 2]
    assert set(graph.inputs[0]) == {"messages", key}


def test_identidad_conservada_turnos_y_nueva_solicitud():
    graph = Graph()
    conversation = Conversation(graph, customer_id=1)
    first = conversation.send("Consulta", customer_id=1)
    first["customer_id"] = 999
    conversation.send("Continuar")
    result = conversation.send("Otra solicitud", new_request=True)
    assert [state["customer_id"] for state in graph.inputs] == [1, 1, 1]
    assert result["customer_id"] == 1
    assert "ticket_id" not in graph.inputs[-1]
    assert len(graph.inputs[-1]["messages"]) == 1


def test_cambio_de_cliente_rechazado_antes_del_grafo():
    graph = Graph()
    conversation = Conversation(graph, customer_id=1)
    conversation.send("Consulta")
    for new_request in (False, True):
        with pytest.raises(ValueError, match="cambiar de cliente"):
            conversation.send("Otra consulta", customer_id=2, new_request=new_request)
    assert len(graph.inputs) == 1
    assert conversation.send("Continuar")["customer_id"] == 1


def test_identidad_no_se_adopta_desde_resultado_del_grafo():
    graph = Graph()
    conversation = Conversation(graph, customer_id=1)
    graph.returned_id = 999
    with pytest.raises(ValueError, match="identidad"):
        conversation.send("Consulta")
    graph.returned_id = None
    result = conversation.send("Reintentar")
    assert result["customer_id"] == 1
    assert len([message for message in graph.inputs[-1]["messages"] if isinstance(message, HumanMessage)]) == 1


def test_consulta_anonima_sin_identidad_ficticia():
    graph = Graph()
    conversation = Conversation(graph)
    assert "customer_id" not in conversation.send("customer_id=123")
    assert "customer_id" not in conversation.send("Otra consulta", new_request=True)
    with pytest.raises(ValueError):
        conversation.send("Cambiar", customer_id=1)
    graph.returned_id = 123
    with pytest.raises(ValueError, match="identidad"):
        conversation.send("Consulta")


def test_aislamiento_entre_clientes():
    graph = Graph()
    first, second = Conversation(graph, customer_id=1), Conversation(graph, customer_id=2)
    first.send("Primero")
    second.send("Segundo")
    result = first.send("Continuar")
    assert result["customer_id"] == 1
    assert all(message.content != "Segundo" for message in result["messages"])
    assert [state["customer_id"] for state in graph.inputs] == [1, 2, 1]


@pytest.mark.parametrize("customer_id", [True, False, 0, -1, "1", 1.0])
def test_identidad_constructor_debe_ser_id_valido(customer_id):
    with pytest.raises(ValueError):
        Conversation(Graph(), customer_id=customer_id)
