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
| Patrón Orquestador / supervisor | `app/agents/orquestador/` | Crea ticket de servicio antes del diagnóstico; persiste la cotización aceptada en ese ticket y deja el pago pendiente | `test_graph_confirmation.py`, `test_orchestrator_sales.py`, contratos de paridad |
| Red descentralizada | `app/agents/decentralized/` | Flujos de cliente y capacidades ADMIN conectados a servicios compartidos; ticket de servicio y cotización respetan el contrato común | `tests/contract/patterns/`, `tests/integration/` |
| «Mis Tickets» del cliente `GET /api/customer/tickets` | `app/adapters/api/chat.py`, `app/database/repository.py` | Lista propia por sesión e incluye tipo y texto de diagnóstico hardware/software, cotizaciones y líneas | Contrato en `specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml` |
| CRUD administrativo de tickets (`/api/admin/tickets`) | `app/adapters/api/admin_tickets.py`, `app/database/repository.py`, `app/accounts/session.py` | Implementado; requiere esquema completo y rol ADMIN | Guía Postman en `contexto/CRUD-tickets-admin-postman.md` |
| CRUD de inventario (`/api/inventory/parts`, `/api/inventory/categories`) | `app/adapters/api/inventory.py`, `app/application/inventory.py`, `app/adapters/persistence/inventory.py`, `app/domain/inventory.py` | Implementado; sesiones de personal ADMIN/TECHNICIAN; usa `spare_parts` y respeta referencias de presupuestos | `tests/contract/test_inventory_contract.py`, `tests/integration/test_inventory_api.py` |
| Trazas en LangSmith (contenido oculto) | `app/main.py` | Listo; se activa con `LANGSMITH_TRACING` | `test_api.py` |
| Trazas locales del Jerárquico | `app/agents/jerarquico/trace.py` | Listo | `test_hierarchical_tracing.py` |
| Correo de recuperación (SMTP u outbox local) | `app/accounts/mailer.py`, `app/email/` | Listo | `test_accounts_recovery.py` |
| Búsqueda en conocimiento (RAG) | `app/rag/`, adaptadores por patrón | Léxica compartida por defecto en los tres patrones; embeddings vectoriales optativos con `RAG_RETRIEVAL_MODE=hybrid` | `test_retriever.py`, `test_knowledge_base.py` |

| Chat autenticado por voz `POST /api/chat/audio` | `app/application/audio_chat.py`, `app/adapters/speech/`, `app/adapters/api/chat.py` | Backend implementado; desactivado por defecto | `test_audio_chat_api.py`, `test_audio_chat_patterns.py` |
| Asientos contables internos (registro, consulta, reversión y trazabilidad; solo ADMIN) | `app/adapters/api/accounting.py`, `app/adapters/persistence/accounting.py`, `sql/migrations/003_accounting_entries.sql` | Implementado; migración aditiva aplicada y verificada en `multiagentedb` de pruebas | `test_accounting_api.py`, `test_accounting_contract.py`, `test_accounting_postgres.py` |
| Catálogo contable y búsqueda de cuentas (solo ADMIN) | `app/adapters/api/accounting_catalog.py`, `app/adapters/persistence/accounting_catalog.py`, migraciones `012`–`013` | Implementado; lista por plan con `q` parcial en código/denominación, filtros ACTIVE/imputable y paginación; PCGE cargado en `multiagentedb` de pruebas | Validación de lectura directa contra el repositorio: plan 1, 1,192 cuentas, 844 activas/imputables; consultas parciales `10`, `efectivo`, `caja` devuelven coincidencias |

## Pendientes conocidos

- El backend entrega todas las categorías activas por `/api/inventory/categories`; el frontend actual todavía tiene cinco opciones fijas y debe consumir esta ruta para exponer toda la taxonomía de la base de datos.

### Patrones multiagente coherentes (Spec Kit)
- Estado de la feature 011: los tres patrones crean tickets para reparación/soporte, guardan la evaluación técnica en el ticket propio y exponen su código mientras la cotización espera confirmación. Al aceptar, guardan la cotización `REPAIR` en ese mismo ticket; el pago queda pendiente y el servicio no reserva stock. El Orquestador crea el ticket al completar la recepción, antes del diagnóstico, y conserva ese mismo ticket en la propuesta y aceptación. Ventas directas y PC_BUILD se cotizan sin ticket; aceptar revalida y reserva stock, dejando el pago pendiente. Los tres comparten políticas de rol, capacidades ADMIN, perfil efectivo de modelo y corpus RAG. Contratos, pruebas unitarias y de integración relacionadas anteriormente aprobadas: 167; contratos aislados: 124. En `multiagentedb`, las migraciones 015 y 016 figuran `RECORDED` en el ledger, verificado el 2026-11-09. Esta iteración no se probó manualmente con Groq/LangSmith ni desde el frontend; la matriz manual está en `docs/30-guia-pruebas-manuales-chat-multirole-frontend.md`.

- Descentralizado persiste la evaluación de Hardware o Software en el ticket asociado al cliente autenticado. Si ambos especialistas actualizan el caso, se conserva el contenido de los dos campos; el `diagnosis_type` refleja el último especialista que guardó su evaluación y no se marca `HYBRID` solo por haber visitado ambos agentes. No requiere migración.

### Asientos contables internos (Spec Kit)

La API administrativa permite listar categorías, crear asientos balanceados en PEN, consultar listado/detalle y revertir un asiento mediante otro vinculado. El actor proviene de la sesión y solo `ADMIN` puede acceder. No se integra con pagos, chat, agentes ni generación PLE. La migración aditiva está en `sql/migrations/003_accounting_entries.sql`; se aplicó y verificó en la BD de prueba `multiagentedb` indicada explícitamente para la ejecución.

### Catálogo de cuentas contables (Spec 009)

`GET /api/admin/accounting/plans/{plan_id}/accounts` admite `q` opcional para buscar parcialmente por código o denominación (`ILIKE`), además de `status`, `postable`, `parent_id` y paginación. Sin `q`, devuelve la primera página ordenada por código. Verificación de lectura en `multiagentedb` el 2026-11-09: el plan PCGE predeterminado tiene 1,192 cuentas; 844 cumplen `ACTIVE` e imputable. Búsquedas parciales por `10`, `efectivo` y `caja` devolvieron coincidencias. No se cambió el backend en esta corrección porque la ruta y la consulta ya respondían correctamente; el frontend ahora carga una primera página automáticamente al elegir el plan y filtra por texto al escribir.

- Se conservan los tres grafos para comparación académica. El RAG común usa búsqueda léxica por defecto: manifiesto de fuentes, metadatos de confianza y procedencia, fragmentación determinista y abstención compartida. FastEmbed y Chroma quedan detrás del modo híbrido optativo y no se cargan en el flujo léxico.
- FAQ de prueba (2026-11-09): el corpus app/agents/jerarquico/knowledge_base/faq_servicio.md contiene valores provisionales; durante pruebas el asistente los comunica directamente, sin decir que son demostrativos. Reemplazar y verificar los datos antes de produccion.
- El Orquestador enruta preguntas informativas al agente FAQ y reutiliza la recuperacion y respuesta comunes con el Jerarquico; precios y stock actuales siguen consultandose desde el catalogo.
- El Descentralizado reconoce preguntas FAQ de ubicación, horarios, servicios, pagos, políticas y pasos para cotizar; responde con el mismo `MarkdownFaqRetriever` y `answer_faq` compartidos. Si falla el proveedor LLM, usa un extracto de la evidencia recuperada en lugar del mensaje genérico de error.
- La solicitud de reembolso puede registrarse como `REQUESTED` tras validar titularidad, pago completado, saldo y duplicados; la resolución sigue siendo manual y no se transfiere dinero desde el chat.
- La compra externa permanece no disponible. No existe una relación de ofertas confiables proveedor-artículo-precio-plazo.

- **Esquema de bootstrap:** `sql/creacion_tablas_ingles_sin_inserciones.sql` es legado y omite objetos actuales. `contexto/tablas postgres v2.sql` se generó desde `multiagentedb` el 2026-11-03 y elimina/recrea los objetos exportados del esquema `public`; usar solo en una BD reinicializable. Para conservar datos, aplicar migraciones. “Mis Tickets” devolvió 200 contra la BD de referencia y serializó los tickets cotizados.
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
| Trazabilidad de stock backend | `app/adapters/persistence/inventory_movements.py`, API `/api/inventory` y migración 20261108 | CRUD admite `current_stock` obsoleto temporalmente y lo convierte en movimiento; frontend debe integrar las rutas dedicadas |
| Esquemas de diagnóstico y repuestos | `jerarquico/schemas.py` y `orquestador/graph/state.py` (`PartRequest`, `TechnicalDiagnosis`) | Campos que se separan con el tiempo |

Módulos fuera del flujo de la aplicación: `app/web.py` (interfaz Streamlit de prueba) y `app/rag/ingest.py` (script de
ingesta, se ejecuta con `python -m`); `app/agents/sales.py` y `app/tracing.py` se usan en pruebas y en el patrón de referencia.
