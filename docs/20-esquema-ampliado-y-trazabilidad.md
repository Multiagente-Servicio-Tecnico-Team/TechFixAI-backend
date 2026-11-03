# Esquema ampliado y trazabilidad

## Verificación del 2026-11-02

Se comparó en modo de solo lectura la estructura de la base de prueba configurada localmente con `contexto/tablas postgres v2.sql`. Se revisaron nombres de tablas y columnas, enums y restricciones; no se consultaron filas de negocio ni se imprimieron credenciales o la URL de conexión.

La base contiene las entidades ampliadas de usuarios, tickets, cotizaciones y detalles, repuestos, pagos, solicitudes de reembolso, garantías y reclamos, logística, proveedores y órdenes de compra. Los estados y columnas relevantes coinciden con el esquema ampliado para los flujos revisados.

**Resultado:** no se necesitó DDL ni migración en esta revisión. No se ejecutó `contexto/tablas postgres v2.sql`: ese archivo contiene `DROP ... CASCADE` y sirve como referencia de bootstrap destructivo, no como migración de una base existente.

La conciliación estática de las consultas y estados usados por `ServiceRepository` confirma los nombres del esquema ampliado: `payments.payment_code` y `payments.customer_id` para resolver pagos del cliente; `refunds.payment_id`, `ticket_id`, `amount`, `reason` y `refund_status_enum`; `PAYMENT_PENDING` y `CANCELLED` para tickets; además de los campos y enums de reclamos de garantía y logística. La prueba de contrato valida columnas y etiquetas concretas en `tests/unit/infrastructure/test_expanded_schema_contract.py`, y la búsqueda de pago verifica el filtro simultáneo por código y cliente.

No se encontró una columna o etiqueta enum requerida ausente. El flujo de compras a proveedores no escribe en `purchase_orders` ni `purchase_order_items`, porque el sistema no tiene una oferta de proveedor asociada a un repuesto.

## Auditoría de duplicados

La búsqueda de referencias en `app/`, `tests/` y el árbol del proyecto confirmó que `app/rag/retriever.py::buscar_conocimiento` no tenía callers: las herramientas ya consumían `retrieve_documents`. Se retiró ese adaptador muerto. Se conservaron `MarkdownKnowledgeRetriever` porque convierte casos técnicos estructurados en candidatos de catálogo; `retrieve_technical_knowledge` porque el nodo técnico del Orchestrator lo usa como adaptador del RAG común; los wrappers de cotización porque ventas de Jerárquico y Orchestrator aún los importan y delegan los cálculos a `app/application/quotes.py`; y `app/config.py::create_chat_model` porque agentes existentes lo importan. No se retiraron grafos ni herramientas cuyo uso dependa de la evaluación académica.

## Decisiones operativas reflejadas en la especificación

- Compras externas quedan no disponibles mientras no exista una oferta confiable por proveedor, repuesto, precio y plazo.
- Un reembolso solo puede registrarse como solicitud pendiente (`REQUESTED`), con resolución manual posterior. El chat no cambia el estado del pago ni mueve dinero.
- El FAQ de `app/agents/jerarquico/knowledge_base/faq_servicio.md` contiene datos marcados como demostrativos; el contexto recuperado debe conservar esa etiqueta y no presentarlos como hechos operativos.
- Los tres grafos se conservan para evaluación. Las capacidades compartidas se centralizan sin unir las topologías.

## Registro de cambios de esquema

| Fecha | Base | Cambio | Evidencia |
|---|---|---|---|
| 2026-11-02 | Base local de prueba | Ninguno; verificación de solo lectura | Coincidencia estructural con el esquema ampliado; prueba estática en `tests/unit/infrastructure/test_expanded_schema_contract.py` |

## Validación de implementación

Validación ejecutada el 2026-11-02:

- `python -m pytest -p no:cacheprovider tests/contract -q`: 1 passed.
- `python -m pytest -p no:cacheprovider tests/unit -q`: 164 passed.
- `python -m pytest -p no:cacheprovider tests/unit/rag tests/unit/application/test_refund_requests.py tests/unit/infrastructure/test_expanded_schema_contract.py tests/unit/agents/test_faq_retriever.py tests/unit/agents/test_knowledge_base.py tests/unit/agents/test_retriever.py -q`: 25 passed.
- La suite unitaria se repitió con `--basetemp` dentro del proyecto porque el sandbox bloqueó el directorio temporal global de Windows. No se ejecutaron pruebas E2E ni operaciones de escritura en PostgreSQL.

La verificación de esquema documenta la comparación estructural; el cierre de paridad y flujos conversacionales se registra en la sección final de este documento. Cualquier DDL futuro debe ser una migración aditiva versionada, con resumen estructural antes/después y referencia de ticket o decisión.

## Validación incremental de implementación (2026-11-02)

- Contratos de patrones y pruebas de reembolso (repositorio, aplicación e integración): 64 passed.
- Lookup de tickets por cliente autenticado (caso de uso, herramienta descentralizada y detección de intención del Orchestrator): 5 passed en sus pruebas enfocadas; el grafo Orchestrator compila.
- Escenarios de armado de PC jerárquico: 3 passed tras agregar el import faltante de `Decimal` en `app/agents/jerarquico/sales.py`.
- Suite completa: `python -m pytest --basetemp=<directorio-temporal> -p no:cacheprovider --tb=short -q`: 380 passed, 2 warnings. La primera ejecución dentro del sandbox dio errores al crear/limpiar temporales; repetida con permiso de ejecución ampliado terminó correctamente.
- La suite completa inicialmente encontró un fallo de expectativa desactualizada en `test_pattern_api.py` por las claves de metadata sanitizada (`pattern_id`, `scenario_id`, `model_profile_id`) y por el tag `scenario:interactive`; se alineó el test con el contrato vigente.

T031, T039 y T041 fueron completadas: matriz de flujos compartida, integraciones de posventa y perfiles de armado por catálogo en los tres patrones, y validación de efectos sin escrituras inválidas. T052 fue completada con la suite final registrada abajo.

- La suite no requiere Groq, LangSmith ni el modelo de embeddings. Las pruebas usan dobles/fakes con tracing deshabilitado; en algunas pruebas enfocadas el SDK de LangSmith intentó consultar metadatos de conectividad y registró una advertencia de red, sin afectar los resultados. No se ejecutó el smoke test optativo de embeddings descargables.

## Cierre de US3 y validación final (2026-11-02)

- Se centralizaron las reglas de propiedad/estado de garantía en `app/application/warranties.py`, validación de preferencias en `app/application/logistics.py` y selección/modificación de perfiles con precio/stock en `app/application/pc_builds.py`. El módulo histórico jerárquico conserva imports como adaptador.
- Jerárquico, Orchestrator y descentralizado usan las reglas comunes de garantía/logística. Orchestrator resuelve consultas de tickets autenticadas y selección/modificación de armados; el patrón descentralizado incorpora herramientas de ticket, garantía, reclamo, logística y armado que obtienen identidad del estado inyectado.
- `python -m pytest --import-mode=importlib -p no:cacheprovider tests/contract/patterns -q`: 68 passed, 2 warnings.
- Pruebas dirigidas de US3 (reembolsos, tickets, garantías, logística, perfiles de armado y confirmación): 57 passed, 9 deselected, 2 warnings.
- `python -m pytest --basetemp=<directorio-temporal> -p no:cacheprovider --tb=short -q`: **410 passed, 2 warnings**. Se ejecutó con permisos temporales ampliados para el sandbox de Windows.
- No se ejecutó el smoke test optativo que puede descargar el modelo de embeddings. La suite normal no requiere Groq ni LangSmith.

Las 52 tareas de `specs/001-patrones-multiagente-coherentes/tasks.md` están completadas. No se aplicó DDL ni se modificó la base de prueba durante esta fase.