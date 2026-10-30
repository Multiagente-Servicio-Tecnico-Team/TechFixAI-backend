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
| `sql/creacion_tablas_ingles_sin_inserciones.sql` | Esquema de la base de datos (incompleto: ver `features.md`) |
| `sql/migrate_spanish_schema_to_english.sql` | Migración del esquema en español al esquema en inglés |

## Especificaciones (`spec/`) y evidencias (`docs/`), numeradas por tarea

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

La numeración de `spec/` y `docs/` no coincide desde la tarea 07; para una tarea nueva usa el siguiente número
libre en ambas carpetas y regístrala en esta tabla.

## Fuera de este repositorio

- Frontend (pantallas, estilos, pruebas Vitest): [TechFixAI-frontend](https://github.com/SebasBazauri/TechFixAI-frontend), con sus propios `AGENTS.md`, `features.md`, `docs.md` y `memory.md`.
- Producción: frontend en https://techfixai.vercel.app y API en Render (`/backend/*` se reenvía a la API).
