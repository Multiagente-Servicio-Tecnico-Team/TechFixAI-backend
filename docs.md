# Índice de documentación

Dónde está explicado cada tema. Antes de documentar algo nuevo, revisa si ya existe y amplía ese archivo.

## Para empezar

| Documento | Contenido |
| --- | --- |
| `README.md` | Qué es el backend, módulos, arquitectura, configuración, puesta en marcha y pruebas |
| `AGENTS.md` | Reglas para trabajar en el repositorio (personas y agentes de código) |
| `features.md` | Funcionalidades, responsables, pendientes, trabajo en curso y código duplicado |
| `memory.md` | Historial de decisiones y limitaciones, una línea por tarea cerrada |
| `PROGRESO.md` | Avance por etapas del patrón Orquestador y el Jerárquico |

## Por módulo

| Documento | Contenido |
| --- | --- |
| `app/accounts/README.md` | API de cuentas: endpoints, sesión, seguridad y configuración |
| `app/chat/README.md` | Contrato de `POST /api/chat` y cómo conectar un patrón |
| `docs/multiagent-architecture.md` | Diseño del sistema multiagente y del patrón Jerárquico |
| `spec/01-arquitectura-descentralizada.md` | Arquitectura de la Red descentralizada |
| `postman/techfix-auth.postman_collection.json` | Colección de la API de cuentas (Postman o Newman) |
| `contexto/tablas postgres v2.sql` | Script destructivo para reconstruir los objetos del esquema `public` en una BD reinicializable; no contiene datos |
| `sql/creacion_tablas_ingles_sin_inserciones.sql` | Script de bootstrap legado; incompleto y no es fuente de verdad para la base actual |
| `sql/migrate_spanish_schema_to_english.sql` | Migración del esquema en español al esquema en inglés |

## Especificaciones (`spec/`) y evidencias (`docs/`), numeradas por tarea

El contrato backend de audio y su validacion local viven en
[`specs/002-transcripcion-audio/`](specs/002-transcripcion-audio/); el OpenAPI es la referencia para el frontend.

| N.º | Tema | Especificación | Evidencia |
| --- | --- | --- | --- |
| 00 | Plan de trabajo | — | `docs/00-plan.md` |
| 01 | Ventas del patrón Jerárquico | `spec/01-ventas.md` | `docs/01-ventas.md` |
| 02 | Trazabilidad del Jerárquico | `spec/02-trazabilidad.md` | `docs/02-trazabilidad.md` |
| 03 | Chat autenticado y cookie de sesión | `spec/03-chat.md` | `docs/03-chat.md` |
| 04 | Validación final de las tres tareas | — | `docs/04-validacion.md` |
| 05 | Frontend: landing, registro e inicio de sesión | `spec/05-frontend-landing-auth.md` | `docs/05-frontend-landing-auth.md` |
| 06 | Integración de patrones en el portal | `spec/06-integracion-patrones.md` | `docs/06-integracion-patrones.md` |
| 07 | API unificada / ajustes de la Red descentralizada | `spec/07-api-unificada.md` | `docs/07-ajustes-ejecucion-red-descentralizada.md`, `docs/09-api-unificada.md` |
| 08 | Resiliencia del triage Jerárquico / configuración local del frontend | `spec/08-resiliencia-triage-jerarquico.md` | `docs/11-resiliencia-triage-jerarquico.md`, `docs/08-configuracion-frontend-local.md` |
| 09 | Candidato de inventario para diagnóstico | `spec/09-candidato-de-inventario-para-diagnostico.md` | `docs/12-candidato-inventario-diagnostico.md` |
| 10 | Alternativas del catálogo desde el RAG / proxy de Netlify | `spec/10-alternativas-rag-por-familia.md` | `docs/13-alternativas-rag-por-familia.md`, `docs/10-proxy-netlify.md` |
| 11 | Ventas y armado de PC flexible | `spec/11-ventas-y-armado-pc-flexible.md` | `docs/14-ventas-y-armado-pc-flexible.md` |
| 12 | Catálogo de procesadores y RAG técnico | `spec/12-catalogo-de-procesadores-y-rag-tecnico.md` | `docs/15-catalogo-procesadores-y-rag-tecnico.md` |
| 13 | Diagnóstico seguro de fallos del grafo | `spec/13-diagnostico-seguro-de-fallos.md` | `docs/16-diagnostico-seguro-de-fallos.md` |
| 14 | Datos comerciales y FAQ de demostración | `spec/14-datos-comerciales-faq-demo.md` | `docs/17-datos-comerciales-faq-demo.md` |
| 15 | «Mis Tickets» del cliente | `spec/15-mis-tickets-cliente.md` | `docs/18-mis-tickets-cliente.md` |
| 16 | Precios y deduplicación del catálogo | `spec/16-precios-y-dedupe-catalogo-seed.md` | `docs/19-precios-y-dedupe-catalogo-seed.md` |
| 21 | Registro interno de asientos contables | `specs/003-asientos-contables/` | `docs/21-asientos-contables.md` |
| 24 | API CRUD del inventario para el taller | `specs/005-api-inventario/` | `docs/24-api-inventario.md` |
| 25 | Limpieza verificada de auxiliares de migración y tabla sin consumidor | `sql/migrations/010_remove_obsolete_tables.sql` | `docs/25-limpieza-tablas-obsoletas.md` |
| 26 | Desactivación temporal de guardas contables en la base local de pruebas | `sql/operations/accounting-test-triggers-disable.sql`, `accounting-test-triggers-restore.sql` | `docs/26-borrado-temporal-asientos-prueba.md` |
| 27 | Propuesta de mejoras del backend inspiradas en Dolibarr | — | `docs/27-propuesta-mejoras-backend-basadas-dolibarr.md` |
| 28 | Trazabilidad de movimientos de inventario | `specs/008-trazabilidad-movimientos-inventario/` | `docs/24-api-inventario.md` |

La numeración de `spec/` y `docs/` no coincide desde la tarea 07; para una tarea nueva usa el siguiente número
libre en ambas carpetas y regístrala en esta tabla.

## Fuera de este repositorio

- `../dolibarr/TECHFIXAI-ERP-REFERENCE.md`: mapa de referencia del código local de Dolibarr 25, con módulos ERP, informes, planes contables y generación PDF/ODT; es una orientación, no una auditoría de una instancia configurada.

### Trabajo de esta rama (`feature/spec-kit`)

- `specs/001-patrones-multiagente-coherentes/`: especificación, plan, investigación, contratos, quickstart y tareas de paridad académica entre los tres patrones.
- `specs/002-transcripcion-audio/`: especificación, contrato OpenAPI y tareas de transcripción de audio para el backend.
- `specs/003-asientos-contables/`: especificación, plan, contrato, tareas e implementación backend del registro interno de asientos; migración aplicada y validada en la BD PostgreSQL de prueba.
- `specs/009-catalogo-cuentas-consultas-contables/`: contrato OpenAPI, especificación y quickstart del catálogo, periodos y reportes contables; `GET /api/admin/accounting/plans/{plan_id}/accounts` busca por código/denominación y admite filtros y paginación.
- `docs/20-esquema-ampliado-y-trazabilidad.md`: comparación estructural de solo lectura con `contexto/tablas postgres v2.sql` y registro de validación.

- Frontend (pantallas, estilos, pruebas Vitest): [TechFixAI-frontend](https://github.com/SebasBazauri/TechFixAI-frontend), con sus propios `AGENTS.md`, `features.md`, `docs.md` y `memory.md`.
- Producción: frontend en https://techfixai.vercel.app y API en Render (`/backend/*` se reenvía a la API).
