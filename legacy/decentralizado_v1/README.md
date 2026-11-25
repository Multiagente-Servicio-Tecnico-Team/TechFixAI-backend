# Red descentralizada v1 (archivada)

Implementación anterior del patrón Red descentralizada: agentes con LLM y
herramientas de transferencia (`soporte`, `tecnico`, `ventas`, `almacen`,
`facturacion`...), estado `AgentState`, auditoría de handoffs, operaciones de
ticket/pago/garantía en dos fases y checkpoint en PostgreSQL
(`app/database/decentralized_*`).

Se reemplazó el 2026-11-09 por `app/agents/decentralized/network.py`: la red
ahora reutiliza los agentes de trabajo del Jerárquico (`make_worker_nodes`) y
solo cambia la coordinación (pares que se transfieren el trabajo con
`Command(goto=...)`, validado contra `ALLOWED_HANDOFFS`, sin supervisor).

Se archivó en lugar de borrarse porque incluye trabajo de la spec 011 sin
commit. Las rutas dentro de esta carpeta replican las originales:

- `app/...` → código archivado (incluye el adaptador v1 en
  `app/adapters/patterns/decentralized.py`).
- `tests/...` → pruebas que solo cubrían ese código y copias íntegras de las
  pruebas de contrato antes de adaptarlas al estado compartido.

No se importa desde `app/` ni se ejecuta con `pytest` (`testpaths` solo incluye
`tests/unit` y `tests/integration`). Para restaurar un archivo, muévelo de vuelta
a la misma ruta relativa en la raíz del proyecto.
