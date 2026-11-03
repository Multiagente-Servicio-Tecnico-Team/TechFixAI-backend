"""Conversación en memoria, independiente por instancia y sin registrar mensajes."""
from copy import deepcopy
from threading import Lock

from langchain_core.messages import HumanMessage
from langsmith import tracing_context


class Conversation:
    """Un objeto por conversación. El consumidor conserva la instancia entre turnos.

    No ofrece autenticación ni persistencia: reiniciar el proceso pierde el estado.
    new_request=True inicia otra solicitud y descarta diagnóstico e inventario previos.
    customer_id procede del consumidor autenticado y permanece ligado a la
    instancia incluso al iniciar otra solicitud. Omitirlo conserva el uso anónimo.
    """

    def __init__(self, graph, *, customer_id: int | None = None):
        # Solo el consumidor autenticado proporciona este dato; no el modelo.
        if customer_id is not None and (type(customer_id) is not int or customer_id <= 0):
            raise ValueError("Identidad de cliente inválida")
        self.graph = graph
        self._customer_id = customer_id
        self._state = {}
        self._lock = Lock()

    def send(self, message: str, *, new_request: bool = False, customer_id: int | None = None):
        """customer_id, si se aporta, solo comprueba la identidad ya vinculada."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Escribe un mensaje no vacío.")
        with self._lock:
            if customer_id is not None and (type(customer_id) is not int or customer_id != self._customer_id):
                raise ValueError("La conversación no permite cambiar de cliente")
            state = {} if new_request else deepcopy(self._state)
            state.pop("customer_id", None)
            if self._customer_id is not None:
                state["customer_id"] = self._customer_id
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
                result = self.graph.invoke(state, config={"recursion_limit": 100})
            returned_id = result.get("customer_id")
            if returned_id is not None and (type(returned_id) is not int or returned_id != self._customer_id):
                raise ValueError("El grafo devolvió una identidad de cliente incompatible")
            result = deepcopy(result)
            if self._customer_id is not None:
                result["customer_id"] = self._customer_id
            else:
                result.pop("customer_id", None)
            self._state = deepcopy(result)
            return deepcopy(result)
