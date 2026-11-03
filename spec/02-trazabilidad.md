# 02 — Trazabilidad jerárquica

**Estado retrospectivo: Implementada según código y evidencia documentada; límites operativos pendientes.**
**Evidencia revisada:** docs/02-trazabilidad.md; app/agents/jerarquico/trace.py; tests/unit/agents/test_hierarchical_tracing.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Correlacionar la ruta de cada ejecución del patrón, los agentes llamados y las
herramientas PostgreSQL utilizadas para diagnóstico operativo, sin persistir
contenido de conversación ni datos del cliente.

## Contrato de evento

Cada línea JSONL contiene únicamente:

- `timestamp` UTC.
- `execution_id` aleatorio por invocación del grafo.
- `name` tomado de una lista permitida de agentes o herramientas.
- `kind`: `agent` o `tool`.
- `event`: `start`, `success` o `error`.

No registrar mensajes, prompts, respuesta del modelo, parámetros ni resultados
de herramientas, identificadores de cliente/ticket, credenciales o texto de
excepciones. Los errores se propagan al llamador después de registrar el evento
`error`.

## Almacenamiento y validación

La ruta predeterminada es `.local/hierarchical-traces.jsonl`; puede sustituirse
con `HIERARCHICAL_TRACE_PATH`. El archivo debe permanecer fuera del control de
versiones, con permisos de instancia y política de rotación al desplegar.

La prueba comprueba correlación entre nodo y herramienta y verifica que mensajes,
datos de cliente, resultados y texto de excepción no aparecen en el archivo.

Checkpoint de commit del usuario: ____________________
