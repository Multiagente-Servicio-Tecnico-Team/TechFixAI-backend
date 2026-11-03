"""Conversación en memoria, independiente por instancia y sin registrar mensajes."""
from copy import deepcopy
from threading import Lock
from uuid import uuid4

from langchain_core.messages import HumanMessage
from langsmith import tracing_context


class Conversation:
    """Un objeto por conversación. El consumidor conserva la instancia entre turnos.

    No ofrece autenticación ni persistencia: reiniciar el proceso pierde el estado.
    new_request=True inicia otra solicitud y descarta diagnóstico e inventario previos.
    """

    def __init__(self, graph):
        self.graph = graph
        self._state = {}
        self._lock = Lock()
        self._thread_id = str(uuid4())

    def send(self, message: str, *, new_request: bool = False):
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Escribe un mensaje no vacío.")
        with self._lock:
            if new_request:
                self._thread_id = str(uuid4())
            state = {} if new_request else deepcopy(self._state)
            history = list(state.get("messages", []))
            state.update(
                messages=[*history, HumanMessage(content=message.strip())],
                turn_start_index=len(history),
                handoff_count=0,
                handoff_history=[],
                tool_iterations={},
                errors=[],
                next_agent=None,
            )
            # Evita exportar mensajes por variables de trazado del entorno.
            with tracing_context(enabled=False):
                result = self.graph.invoke(
                    state,
                    config={
                        "configurable": {"thread_id": self._thread_id},
                        "recursion_limit": 100,
                    },
                )
            self._state = deepcopy(result)
            return deepcopy(result)
