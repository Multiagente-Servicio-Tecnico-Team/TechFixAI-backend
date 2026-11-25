# Orquestador v1 (archivado)

Implementación anterior del patrón Orquestador, con agentes propios
(`atencion`, `ventas`, `almacen`, `postventa`, `billing`, `sales`...) y estado
`AgentState`. Se reemplazó el 2026-11-09 por
`app/agents/orquestador/graph/hub.py`: el Orquestador ahora reutiliza los
agentes de trabajo del Jerárquico (`make_worker_nodes`) y solo cambia la
coordinación (un supervisor único en estrella).

Se archivó en lugar de borrarse porque incluye trabajo de la spec 011 que aún no
tenía commit. Las rutas dentro de esta carpeta replican las originales:

- `app/agents/orquestador/...` → código archivado
- `tests/...` → pruebas que solo cubrían ese código

No se importa desde `app/` ni se ejecuta con `pytest` (`testpaths` solo incluye
`tests/unit` y `tests/integration`). Para restaurar un archivo, muévelo de vuelta
a la misma ruta relativa en la raíz del proyecto.
