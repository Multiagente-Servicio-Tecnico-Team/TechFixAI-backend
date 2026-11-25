# Inventario y uso de las especificaciones

Estas especificaciones se escribieron durante tareas ya iniciadas y no siguen
por sí solas el ciclo nativo de Spec Kit. Son documentos retrospectivos: los
requisitos describen el comportamiento acordado para cada tarea; el estado y la
evidencia indican cuánto está respaldado por el código/documentación revisados.
No se debe interpretar una especificación histórica como prueba de que todo su
alcance funciona hoy.

## Estado de la revisión

Revisión estática del árbol de trabajo del 2026-11-02. No se ejecutaron pruebas,
servicios externos ni consultas a PostgreSQL. Los resultados de pruebas citados
en `docs/` son evidencia histórica de esas tareas, no ejecuciones de esta revisión.

| Archivo | Estado observado | Evidencia y brecha principal |
|---|---|---|
| `01-ventas.md` | Parcial; revisar contra esquema vigente | `docs/01-ventas.md`, `app/agents/jerarquico/`, `app/database/repository.py`; el flujo está descrito y probado históricamente, pero `features.md` registra fallos de esquema y de guardado que deben comprobarse contra la rama actual. |
| `01-arquitectura-descentralizada.md` | Histórico / parcial | Describe explícitamente `patron-red-rag-aislado`, no necesariamente la integración actual. La Red Descentralizada figura como experimental y con herramientas simuladas en `features.md`. |
| `02-trazabilidad.md` | Implementado según código y evidencia histórica | `app/agents/jerarquico/trace.py`, `tests/unit/agents/test_hierarchical_tracing.py`, `docs/02-trazabilidad.md`. La escritura compartida multiinstancia y la retención siguen siendo operativas. |
| `03-chat.md` | Implementación repartida entre repositorios; despliegue pendiente de smoke test | `app/accounts/`, `app/chat/`, `tests/integration/test_pattern_api.py`, `docs/03-chat.md`; el proxy/cliente está en `TechFixAI-frontend`, no en este repositorio. |
| `05-frontend-landing-auth.md` | Implementado en repositorio separado; documento histórico | `TechFixAI-frontend/` tiene su propio código e instrucciones. La ruta antigua `landing/` y los comandos `npm --prefix landing` ya no describen el backend actual. |
| `06-integracion-patrones.md` | Parcial | Contrato común, selector, sesión y trazas están implementados; la capacidad de cada patrón difiere. `features.md` señala herramientas simuladas en Descentralizado y un fallo conocido al guardar en Orquestador. |
| `07-api-unificada.md` | Implementado según estructura actual | `app/main.py`, `app/accounts/`, `app/adapters/api/`, `tests/integration/test_combined_api.py`. |
| `08-resiliencia-triage-jerarquico.md` | Implementado según evidencia histórica | `app/agents/jerarquico/supervisor.py`, `tests/integration/test_hierarchical_workflows.py`, `docs/11-resiliencia-triage-jerarquico.md`. |
| `09-candidato-de-inventario-para-diagnostico.md` | Implementado según código y evidencia histórica | `app/agents/jerarquico/technical_support.py`, `warehouse.py`, `supervisor.py`, `tests/integration/test_multiagent_graph.py`, `docs/12-candidato-inventario-diagnostico.md`. |
| `10-alternativas-rag-por-familia.md` | Implementado con límites de datos | `app/database/repository.py`, `app/agents/jerarquico/warehouse.py`, `tests/integration/test_hierarchical_workflows.py`, `docs/13-alternativas-rag-por-familia.md`; compatibilidad física no está modelada. |
| `11-ventas-y-armado-pc-flexible.md` | Parcial, alcance acotado | `docs/14-ventas-y-armado-pc-flexible.md`, `app/agents/jerarquico/`; venta, perfiles curados y cambios se describen como cubiertos. No existe armado libre/optimización universal y aceptación no reserva stock. |
| `12-catalogo-de-procesadores-y-rag-tecnico.md` | Implementado según evidencia; el nombre de alcance se quedó corto | `docs/15-catalogo-procesadores-y-rag-tecnico.md`, `app/agents/jerarquico/`; el fallback comercial se generalizó a familias distintas de procesadores. Compras sigue limitada por el esquema. |
| `13-diagnostico-seguro-de-fallos.md` | Implementado según evidencia histórica | `app/agents/jerarquico/trace.py`, `tests/unit/agents/test_hierarchical_tracing.py`, `docs/16-diagnostico-seguro-de-fallos.md`. |
| `14-datos-comerciales-faq-demo.md` | Implementado para demostración; contenido ficticio | `data/knowledge/`, `app/rag/`, `tests/unit/agents/test_faq_retriever.py`, `docs/17-datos-comerciales-faq-demo.md`. No publicar dirección, horario o pagos demo como datos reales. |
| `15-mis-tickets-cliente.md` | Parcial; verificar contra el esquema actual | `app/adapters/api/`, `app/database/repository.py`, `tests/integration/test_portal.py`, `docs/18-mis-tickets-cliente.md`; `features.md` registra 503 al listar tickets con presupuesto. |
| `16-precios-y-dedupe-catalogo-seed.md` | Cambio del seed documentado; BD existente no se actualiza sola | `docs/19-precios-y-dedupe-catalogo-seed.md` y archivo SQL de seed; requiere migración explícita si se quiere modificar una BD ya poblada. |

## Cómo llevar cambios nuevos al flujo nativo de Spec Kit

La instalación actual usa `specs/` como raíz de features. Para una funcionalidad
nueva, abre el backend como raíz del proyecto y solicita en Codex el flujo
`speckit-specify` → revisión → `speckit-plan` → revisión → `speckit-tasks`.
La salida estándar será `specs/NNN-nombre/spec.md`, `plan.md` y `tasks.md`. En Codex, invoca las habilidades disponibles con `$speckit-specify`, `$speckit-plan` y `$speckit-tasks`; describe el alcance y vincula los antecedentes de `spec/`.
Después de generar tareas se puede usar `speckit-analyze`; esa habilidad exige
los tres artefactos y es de solo lectura.

El `.gitignore` actual excluye `.agents/` y `.specify/`: la instalación funciona localmente, pero el equipo no recibirá esos archivos al clonar. Si quieres compartir las habilidades y plantillas, deja de ignorar esas carpetas y agrégalas al repositorio en un cambio separado.

No generes planes ni tareas retroactivas para funcionalidades que ya existen.
Para una mejora de una capacidad existente, crea una feature nueva con el cambio
futuro como alcance, enlaza la especificación histórica y describe en `spec.md`
solo el comportamiento deseado y verificable. Mantén aquí los documentos
históricos hasta decidir una migración completa.

## Criterio de actualización

Al cerrar una implementación, actualiza el estado/evidencia de la especificación
afectada y su documento `docs/NN-*.md`. Revisa también `features.md`, porque hoy
contiene estados y fallos conocidos con fecha anterior a esta revisión. No copies
un criterio histórico como validación actual sin volver a ejecutarlo.
