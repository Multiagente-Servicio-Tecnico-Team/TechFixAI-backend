# 02 — Trazabilidad del patrón jerárquico

El módulo `app/agents/jerarquico/trace.py` registra nodos y operaciones de
base de datos en JSONL. El nodo supervisor raíz genera un UUID aleatorio
`execution_id`; el estado lo propaga a los siguientes nodos y herramientas.

Los nombres se validan con allowlists. Los registros omiten estado LangGraph,
mensajes, parámetros de consulta, resultados, correos, IDs de cliente/ticket y
texto de excepciones. Los fallos de los nodos/herramientas se vuelven a lanzar
después de anotar solo el evento `error`.

Ruta local por defecto: `.local/hierarchical-traces.jsonl`; se puede seleccionar
otra ubicación mediante `HIERARCHICAL_TRACE_PATH`. La escritura JSONL usa un
bloqueo de proceso. Para despliegue con múltiples procesos/instancias, se requiere
un backend de eventos compartido y rotación/retención; no exponer el archivo por
HTTP.

Prueba: `tests/test_hierarchical_tracing.py`. La suite jerárquica enfocada
incluye **48 pruebas aprobadas** en total.

Checkpoint de commit del usuario: ____________________
