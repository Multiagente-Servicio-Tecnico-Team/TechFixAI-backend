# Funcionalidades del backend

Qué existe, dónde está, quién lo mantiene y en qué estado. Actualízalo cuando agregues o cambies una
funcionalidad. Estado al 2026-10-20 (rama `develop`).

## Responsables por carpeta

| Carpeta | Responsable principal | También participan |
| --- | --- | --- |
| `app/accounts/` (registro, login, recuperación, sesión) | SebasBazauri | jsalinas4 |
| `app/chat/` (contrato de `/api/chat`, patrón de referencia) | SebasBazauri | jsalinas4 |
| `app/main.py` (API unificada; único punto de entrada) | jsalinas4 | SebasBazauri, johstevnn |
| `app/agents/jerarquico/` (patrón Jerárquico) | jsalinas4 | — |
| `app/agents/orquestador/` (patrón Orquestador) | johstevnn | jsalinas4 |
| `app/agents/decentralized/` (Red descentralizada) | Jose Saldaña | jsalinas4 |
| `app/database/` (repositorio PostgreSQL) | jsalinas4 | Jose Saldaña, johstevnn |
| `app/rag/` (ingesta y búsqueda vectorial) | Jose Saldaña | — |
| `app/email/` (correo SMTP) | SebasBazauri | Jose Saldaña |
| `sql/` (esquema de base de datos) | jsalinas4 | — |
| `postman/` (colección de cuentas) | SebasBazauri | — |

## Funcionalidades

| Funcionalidad | Dónde | Estado | Pruebas |
| --- | --- | --- | --- |
| Registro de cuenta (abre sesión al registrar) | `app/accounts/api.py` | Listo | `test_accounts_api.py` |
| Inicio y cierre de sesión con cookie HttpOnly firmada | `app/accounts/` | Listo | `test_accounts_api.py`, `test_session_guard.py` |
| Límite de 5 intentos de login cada 15 min | `app/accounts/security.py` | Listo | `test_accounts_api.py` |
| Recuperar y restablecer contraseña (enlace de 15 min, un solo uso) | `app/accounts/` | Listo | `test_accounts_recovery.py` |
| API unificada (`/auth` + `/api`, un proceso y un origen) | `app/main.py` | Listo | `test_combined_api.py` |
| Chat autenticado `POST /api/chat` con selector de patrón | `app/main.py`, `app/chat/contract.py` | Listo | `test_pattern_api.py`, `test_portal.py` |
| Límite de 20 mensajes por minuto por cliente | `app/main.py` | Listo | `test_pattern_api.py` |
| Patrón Jerárquico (ventas, soporte, almacén, garantía, logística) | `app/agents/jerarquico/` | Funciona; ver pendientes | `test_hierarchical_workflows.py`, `test_multiagent_graph.py` |
| Patrón Orquestador / supervisor | `app/agents/orquestador/` | Cotiza; guardar ticket falla (ver pendientes) | `test_graph_confirmation.py`, `test_quotes.py` |
| Red descentralizada | `app/agents/decentralized/` | Herramientas simuladas en `develop` | `test_decentralized*.py`, `test_conversation.py` |
| «Mis Tickets» del cliente `GET /api/customer/tickets` | `app/main.py`, `app/database/repository.py` | Falla con tickets presupuestados (ver pendientes) | `test_portal.py` |
| Trazas en LangSmith (contenido oculto) | `app/main.py` | Listo; se activa con `LANGSMITH_TRACING` | `test_api.py` |
| Trazas locales del Jerárquico | `app/agents/jerarquico/trace.py` | Listo | `test_hierarchical_tracing.py` |
| Correo de recuperación (SMTP u outbox local) | `app/accounts/mailer.py`, `app/email/` | Listo | `test_accounts_recovery.py` |
| Búsqueda en conocimiento (RAG) | `app/rag/`, retrievers por patrón | Listo | `test_retriever.py`, `test_knowledge_base.py` |

## Pendientes conocidos

- **Esquema SQL incompleto:** `sql/creacion_tablas_ingles_sin_inserciones.sql` no crea `quote_details.custom_item_name`, `diagnosis_type_enum` ni las columnas de diagnóstico. Efecto: «Mis Tickets» responde 503 con tickets presupuestados y el Jerárquico responde 503 al guardar el diagnóstico.
- **Orquestador al aceptar:** `app/agents/orquestador/agentes/ventas.py` espera 4 valores de `create_ticket_with_quote` y `app/database/repository.py` devuelve 3 (`ValueError`, 502).
- **Botón «No guardar»:** la API envía «No, rechazo el presupuesto»; el Orquestador `develop` solo reconoce «no», «rechazo», «cancelar»… La rama `alonso_orquestador` ya acepta frases que empiezan con «no, ».
- **`GROQ_MODEL`:** sin esa variable el Jerárquico no arranca y el Orquestador usa `llama-3.3-70b-versatile`, que Groq ya no reconoce. Usar `openai/gpt-oss-20b`.
- **Prueba conocida que falla:** `test_retriever.py::test_no_unrelated_documents_are_returned`.
- **Despliegue:** Render suspende la API sin tráfico (primera petición ~40 s).

## Trabajo en curso (PR y ramas)

| PR / rama | Qué cambia | Estado |
| --- | --- | --- |
| PR #31 `separar-frontend` | Quita `landing/` (el frontend pasó a TechFixAI-frontend) | Abierto; espera reconectar Vercel |
| PR #32 `feature/clean-architecture` | Capas `domain`, `application`, `adapters`, `infrastructure`; pruebas en `tests/unit`, `tests/integration`, `tests/e2e` | Abierto; en revisión |
| PR #30 (repo anterior) `frontend` | Registro con sesión + negrita en el chat | Abierto; la parte de frontend debe pasar a TechFixAI-frontend |
| Rama `patron-red-rag-aislado` | Red descentralizada con persistencia, pagos, logística y garantía | Sin PR; tiene conflictos con `develop` en `app/main.py` |
| Rama `alonso_orquestador` | Orquestador reescrito como proyecto aparte | Sin PR; no parte de `develop` actual |

PR #31 y #32 comparten un commit de documentación y se pueden fusionar en cualquier orden.

## Código duplicado

Casi no hay código copiado (un solo bloque de 8 líneas, en `decentralized/almacen.py` y `soporte.py`). Lo que sí
se repite es la misma responsabilidad implementada varias veces; antes de crear una versión nueva, usa una de estas:

| Responsabilidad | Implementaciones | Riesgo |
| --- | --- | --- |
| Configuración del entorno | `app/settings.py`, `app/accounts/config.py`, `app/config.py` | Valores por defecto distintos (p. ej. `GROQ_MODEL`) |
| Cálculo de presupuesto | `app/agents/jerarquico/tools/quotes.py`, `app/agents/orquestador/agentes/quotes.py` | Mismo caso, totales distintos según el patrón |
| Búsqueda en conocimiento | `jerarquico/retriever.py`, `orquestador/knowledge/retriever.py`, `rag/retriever.py` | Tres criterios de relevancia |
| Consulta de inventario | `decentralized/tools/almacen_tools.py`, `orquestador/tools/inventory.py`, repositorio | Reglas de stock distintas |
| Esquemas de diagnóstico y repuestos | `jerarquico/schemas.py` y `orquestador/graph/state.py` (`PartRequest`, `TechnicalDiagnosis`) | Campos que se separan con el tiempo |

Módulos fuera del flujo de la aplicación: `app/web.py` (interfaz Streamlit de prueba) y `app/rag/ingest.py` (script de
ingesta, se ejecuta con `python -m`); `app/agents/sales.py` y `app/tracing.py` se usan en pruebas y en el patrón de referencia.
