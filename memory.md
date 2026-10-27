# Memoria del proyecto

Historial de decisiones y limitaciones reales, una línea por tarea cerrada (la más reciente al final).
Antes de programar, lee también `AGENTS.md`, `features.md` y `docs.md`.

Cómo registrar una tarea: agrega al final una línea `- Tema (AAAA-MM-DD): qué se hizo, cómo se validó y qué
limitación queda`, sin datos personales, claves ni textos de excepciones.

Estado al 2026-10-20: el frontend se separó en TechFixAI-frontend (PR #31) y la organización en capas de
Clean Architecture está en revisión (PR #32). Pendientes y responsables en `features.md`.

- Diagnóstico del retiro presencial (2026-10-13): traza local confirma
  `logistics_agent`/`logistics_record_write` exitosos y error en
  `order_completion_agent`/`warranty_write`. LangSmith cambia el texto de error
  a `Provider error details redacted.`; la ejecución antigua no guarda clase ni
  SQLSTATE y no es posible reconstruir la causa exacta. Se verificaron en modo
  lectura las columnas y enums de warranties y la expresión de fecha; no hubo
  escrituras. Añadidos tipo de excepción y SQLSTATE allowlisted a errores JSONL
  locales y al log de API, sin texto SQL/excepción. 13 pruebas de trazabilidad y
  workflows aprobadas, tracing desactivado; diff-check limpio. Evidencia:
  `spec/13-diagnostico-seguro-de-fallos.md` y
  `docs/16-diagnostico-seguro-de-fallos.md`.

- Consulta genérica de catálogo (2026-10-13): si Groq clasifica como FAQ una
  pregunta de disponibilidad/stock/precio/compra, el supervisor ahora recupera
  términos de producto del último mensaje y la envía al lookup comercial de
  PostgreSQL; cubre RAM/SSD/GPU y conserva el caso especial de procesadores.
  Regresión «¿Tienen RAM disponible?» incluida. Validación de workflows,
  grafo y repositorio: 58 aprobadas. Dos pruebas de trazabilidad no prepararon
  `tmp_path` por permisos Windows; ejecutadas las demás suites con
  `.local/pytest-chat-review` como basetemp. No se ejecutó Groq: `.env` tiene
  LangSmith con ocultamiento de inputs/outputs apagado. `SELECT 1` funcionó y
  no hubo escrituras. Límite real: el armador conserva dos perfiles curados y
  no crea builds libres ni optimiza componentes al presupuesto. Evidencia:
  adenda a `spec/12-catalogo-de-procesadores-y-rag-tecnico.md` y
  `docs/15-catalogo-procesadores-y-rag-tecnico.md`.
- Preferencia de armado confirmada (2026-10-13): al exceder presupuesto, conservar
  el uso solicitado y explicar diferencia; no cambiar a un perfil inferior sin
  petición. `.env` local ahora oculta inputs/outputs de LangSmith. Smoke real
  Groq/LangSmith para disponibilidad de RAM acabó en selección pendiente con 20
  opciones; la creación de ticket fue sustituida en memoria, sin escritura a BD.
  La traza remota fue redactada. Suite aislada final: 59 aprobadas con tracing
  desactivado; pruebas trace con tmp_path siguen fallando por permisos Windows.

- Configuración local del frontend (2026-10-07): originalmente las APIs se configuraron en los puertos 8000 y 8001. El bloque de API unificada reemplazó esa configuración por `VITE_API_URL=http://localhost:8000/auth` y `VITE_CHAT_URL=http://localhost:8000`; `landing/.env` continúa ignorado por Git.
- Proxy para Netlify (2026-10-07): se agregó `landing/public/_redirects` para proxy `/backend/*` al backend unificado Render y fallback SPA. Las variables de Netlify deben ser `VITE_API_URL=/backend/auth` y `VITE_CHAT_URL=/backend`, y el sitio debe reconstruirse. Evidencia: `docs/10-proxy-netlify.md`. Pendiente comprobar las cookies desde el dominio Netlify en un deploy real.
- Base inicial: Python, correo SMTP y conexión SQLAlchemy; sin API ni portal.
- Se conservan los servicios existentes. El nuevo flujo no depende de ellos.
- Orden acordado: ventas → trazabilidad → chat → validación y compilación final.
- Catálogo local de demostración, moneda PEN, precios finales sin impuestos adicionales.
- Tarea 1 completada: grafo de ventas y herramienta de catálogo; 3 pruebas aprobadas.
- Tarea 2 completada: callbacks JSONL, llamadas correlacionadas, fallo controlado y concurrencia; 3 pruebas aprobadas.
- Tarea 3 completada: portal FastAPI, sesiones y usuarios con hashes; 6 pruebas aprobadas.
- Prueba real en Edge headless aprobada: login, envío/respuesta, presupuesto, recarga de historial, viewport móvil y logout.
- Limitaciones: catálogo y orientación deterministas de prueba; sesiones e historial en memoria; no conectado a identidad de PostgreSQL.
- Cierre 2026-10-02 (America/Lima): 12 pruebas integradas aprobadas; `compileall` sin errores; `pip check` sin incompatibilidades; JavaScript validado.
- Evidencia local regenerable: `.local/quote-example.json`, `.local/acceptance-traces.jsonl`, capturas desktop/mobile. Se excluye de Git por ser salida de ejecución.
- Servidor temporal de pruebas detenido después de validar el navegador.
- Tarea frontend (rama `frontend`, antes `landing-page`): spec 05 = landing, registro, acceso y recuperación en React según Figma, con cliente HTTP para `POST /registro`, `/login`, `/recuperar` (simulador si no hay `VITE_API_URL`). 39 pruebas Vitest y build aprobados; revisión 2026-10-05 agregó restablecer contraseña, redirección con sesión y consulta nueva desde el chat. Limitaciones: sin backend, sin hash ni BD (specs siguientes). Numeración 05 porque `origin/main` ya usa 01-04.
- Bloque 15 (2026-10-06): selector React integrado con API autenticada para Jerárquico, Orquestador y Descentralizado; el patrón no se puede cambiar a mitad de conversación. LangSmith configura tags, ocultamiento de inputs/outputs y redacción de errores; metadatos explícitos solo incluyen patrón y UUID de conversación, nunca identidad del cliente. La API de cuentas normaliza URL genéricas de PostgreSQL al driver pg8000 declarado por el proyecto. Suite aislada ampliada (excluye scripts PostgreSQL, SMTP y E2E Groq): 180 pruebas aprobadas; 57 Vitest aprobadas con timeout ampliado a 15 segundos bajo carga; build Vite, `pip check`, `compileall`, Pylance y `git diff --check` correctos. Arranque local: landing y OpenAPI de ambas APIs responden 200, ruta de patrones requiere autenticación (401 sin cookie); PostgreSQL `SELECT 1` responde. Los servidores locales están activos; la sesión de login usa un secreto efímero compartido y la cookie no es Secure para localhost HTTP, por lo que se invalida al detener/reiniciar las APIs. No se ejecutó una conversación con Groq ni se mandaron trazas. Limitaciones: Descentralizado mantiene herramientas simuladas/no persiste; conversaciones y ownership están en memoria. `npm audit --omit=dev` muestra 2 vulnerabilidades moderadas en React Router, con remediación sugerida que implica evaluar major v7. Commit pendiente del usuario.
- Corrección de ejecución del patrón descentralizado (2026-10-07): requirements raíz ahora incluye los agentes y RAG; se reparó la fábrica de grafo faltante, los controles de turno se reinician desde el checkpoint API y `Conversation` conserva/rota su `thread_id` correctamente. Se generó el índice Chroma ignorado por Git. Validación: 112 pruebas aisladas aprobadas, `pip check` limpio, recuperación documental devuelve fuentes esperadas y diagnósticos Pylance limpios. No se invocó Groq, PostgreSQL ni LangSmith; las pruebas `test_rag_*` que requieren proveedores/modelos reales quedan fuera de la suite aislada. Detalle: `docs/07-ajustes-ejecucion-red-descentralizada.md`. Commit pendiente del usuario.
- API unificada (2026-10-07): `app.combined:create_app --factory` monta cuentas en `/auth` y conserva chat en `/api/chat`, compartiendo `AccountSettings` y la misma fábrica SQLAlchemy con `SessionGuard`. Se actualizó el frontend local y las guías de ejecución; no se crearon archivos de despliegue. Validación: 29 pruebas Python de cuentas/chat/unificación, 11 pruebas de registro frontend, build Vite y chequeos de sintaxis Pylance aprobados. No se probaron Groq, LangSmith ni PostgreSQL real. El intento inicial de la suite completa de Vitest tuvo un timeout en una prueba de registro (5 s), que pasó aislada después. Evidencia: `spec/07-api-unificada.md` y `docs/09-api-unificada.md`. Commit pendiente del usuario.
- Patrón jerárquico — ventas (checkpoint pendiente): grafo con equipos comercial, técnico y operaciones y nueve agentes especializados según `contexto/Patrones.md`; venta directa consulta catálogo, pide aceptación y crea pago pendiente. Diagnóstico se persiste en las columnas actuales `hardware_diagnosis`/`software_diagnosis`; `provisional_diagnosis` se mantiene solo como dato interno/provisional. Verificado el esquema local por introspección y 48 pruebas aisladas enfocadas aprobadas. No se hicieron escrituras reales a PostgreSQL ni llamadas reales a Groq. Limitaciones confirmadas en esa etapa: el esquema no registra compatibilidad para armado PC ni ofertas de proveedores; no se reserva inventario; pago generado se mantiene `PENDING`. La implementación posterior descrita a continuación incorpora la garantía de venta/armado tras registrar logística.
- Patrón jerárquico — trazabilidad (checkpoint pendiente): eventos JSONL correlacionados por UUID en `.local/hierarchical-traces.jsonl` (o `HIERARCHICAL_TRACE_PATH`). Solo timestamp, execution ID, nombre allowlist, clase de componente y evento; nunca mensajes, credenciales, entradas/resultados de herramientas, IDs de cliente/ticket o texto de excepción. Pruebas de éxito y error validan privacidad. Limitación real: almacenamiento local por proceso; despliegue con varias instancias necesita backend compartido y retención/rotación.
- Orden de cierre vigente: ventas → trazabilidad → corregir y validar el envío de cookie en chat autenticado al final. No se hizo commit; queda checkpoint para el usuario.
- Implementación posterior de venta/armado flexible: búsqueda natural SQL parametrizada, perfiles RAG existentes con siete componentes para oficina/estudio (S/ 655 con ensamble) y ocho para gaming (S/ 920 con ensamble, según la lectura local), cambio de componentes con selección y recotización, y garantía idempotente de 3 meses tras logística para ventas/armados. No se agregaron productos ni se escribieron datos de prueba. Pago continúa `PENDING`, logística `PENDING_RECEIPT`; la GPU aún requiere validar dimensiones/conectores/consumo con fabricante. Suite aislada enfocada: 57 pruebas; Pylance y diff-check limpios. Evidencia: `spec/11-ventas-y-armado-pc-flexible.md` y `docs/14-ventas-y-armado-pc-flexible.md`; commit pendiente.
- Chat autenticado (hecho después de ventas y trazabilidad): auth/chat conservan `credentials: "include"`; las bases de URL de build de producción ahora obligan el proxy same-origin `/backend/auth` y `/backend` cuando la variable está vacía o es absoluta. Esto evita cookies `SameSite=Lax` cross-site entre Netlify y Render; no se cambió la política de cookie a `SameSite=None`. Validación: 61 pruebas Vitest/7 archivos y build Vite aprobados. No se hizo deploy: transmisión real de `Set-Cookie`/`Cookie` en Netlify sigue pendiente de smoke test en el dominio publicado.
- Corrección de ciclo REPAIR/SUPPORT en el patrón jerárquico (commit pendiente): el supervisor crea el ticket `NEW` durante el triage; soporte hardware/software actualiza ese mismo ticket con `diagnosis_type` y la columna diagnóstica correspondiente, y lo deja `IN_DIAGNOSIS`. Aceptar la cotización pasa por facturación y registra cotización `ACCEPTED`, pago `PENDING` y estado final `PAYMENT_PENDING` en una transacción; rechazar cancela el ticket sin crear cotización/pago. La tarifa predeterminada de mantenimiento/reparación quedó alineada a S/ 35.00 del prompt; `LABOR_MAINTENANCE_PRICE` todavía puede sobreescribirla, así que hay que verificar la variable configurada en despliegue. Validación aislada actualizada: 60 pruebas aprobadas. No se escribieron datos en PostgreSQL ni se hizo commit. La compatibilidad de armado PC, las ofertas de proveedores y el smoke test de cookie en Netlify siguen limitados por datos/deploy externos.
- Alternativas para RAG del patrón jerárquico (checkpoint de commit pendiente): todas las guías ahora especifican búsqueda de catálogo por familia, opciones activas con stock/precio, selección del cliente y confirmación técnica de compatibilidad. El caso de RAM permite elegir candidato solo con evidencia y el flujo reconsulta el SKU seleccionado. Solo el SKU exacto se trata como coincidencia directa; coincidencias difusas no ocultan variantes. Prueba real de lectura en PostgreSQL de pruebas: diez opciones RAM Desktop/Laptop sin `TOOL-ESD`; ventiladores con varios SKU disponibles; no hay batería de laptop cotizable (la coincidencia CMOS/RTC se excluye). El catálogo no valida generaciones/formato/modelo RAM. Sin escrituras. Pruebas enfocadas: 49/49 aprobadas; Pylance sin errores. Especificación: `spec/10-alternativas-rag-por-familia.md`; evidencia: `docs/13-alternativas-rag-por-familia.md`. Commit pendiente del usuario.
- Corrección del fallo de `required_parts: null` en el patrón jerárquico: las trazas sitúan los intentos fallidos dentro de `customer_care_supervisor`, y el error de Groq indicaba rechazo de la lista nula durante la validación remota del tool call. La clasificación de intake y el diagnóstico técnico ahora usan JSON mode con JSON Schema en las instrucciones y validación Pydantic local; `required_parts` mantiene tipo array en el esquema y los validadores convierten `null` a `[]`. Suite jerárquica enfocada completa: 61 aprobadas; prueba directa confirma ambas instancias devuelven listas vacías. `git diff --check` correcto. Falta comprobar el prompt con Groq real después de reiniciar el backend.
- Corrección de consulta de catálogo (2026-10-13): preguntas de modelos/precios Intel Core i5 que el clasificador devolvía como FAQ ahora se reconducen a venta y consulta parametrizada de PostgreSQL; la serie/generación se preserva y no se repiten productos de memoria. Lectura local: i5-12400F S/ 145, i5-13400F S/ 210, i5-14400 S/ 230; para 13.ª generación solo consta i5-13400F con stock 5. RAG Markdown compartido alimenta ambos agentes técnicos; se comprobó hardware y se añadió caso software 0x0000007B. Auditoría: los nueve roles están representados, pero Compras no puede cotizar proveedores porque `suppliers` no se relaciona con `spare_parts`, y los supervisores de equipo son enrutadores deterministas. Cuatro suites enfocadas: 59 pruebas aprobadas; sin escrituras a PostgreSQL. Evidencia: `spec/12-catalogo-procesadores-y-rag-tecnico.md`, `docs/15-catalogo-procesadores-y-rag-tecnico.md`; commit pendiente.
- Error 502 en el triage jerárquico: prueba real con Groq reprodujo una clasificación `service` sin `title` o `failure_description`, que el supervisor convertía en `ValueError`. Ahora se usa un título genérico y, si falta la descripción, el texto del mensaje actual; sin mensaje disponible se pide aclaración antes de crear ticket. Prueba de regresión añadida. El grafo completo terminó correctamente con Groq y LangSmith bajo ocultamiento forzado de inputs/outputs (`route=service`, `outcome=awaiting_confirmation`); además, `POST /api/chat` devolvió HTTP 200 usando un guard aislado y repositorio de prueba. No se escribieron datos en PostgreSQL y no se probó la cookie real. Evidencia: `spec/08-resiliencia-triage-jerarquico.md` y `docs/11-resiliencia-triage-jerarquico.md`; commit pendiente.
- Recomendación de SSD para equipo lento: RAG reproduce los casos 10 y 5 del [manual_servicio.md](./app/agents/jerarquico/knowledge_base/manual_servicio.md), ambos con candidato `SSD_1TB`. El prompt de soporte forzaba `required_parts=[]` para diagnóstico y el agente también eliminaba toda pieza en esa rama, por eso solo cotizaba S/ 50 de diagnóstico. Ahora pasa el único artículo del caso RAG principal al almacén aunque la labor siga siendo diagnóstico; stock/precio solo salen del catálogo y la compatibilidad se presenta como pendiente. En BD de prueba no existe el código exacto `SSD_1TB`, pero hay opciones de unidades SSD; para varias opciones se guarda selección pendiente, el cliente responde con código y el grafo continúa a cotización y luego confirmación. `solo diagnóstico` sigue disponible. La búsqueda real también encontró carcasa USB por coincidencia parcial, excluida del listado de unidades SSD. Prueba real con Groq y lecturas de BD terminó en `awaiting_inventory_selection`; se simularon tickets/cotizaciones, sin escrituras DB. Suite enfocada: 47 aprobadas. Evidencia: `spec/09-candidato-de-inventario-para-diagnostico.md`, `docs/12-candidato-inventario-diagnostico.md`; commit pendiente.
- Armados y ventas flexibles (2026-10-13): tres perfiles gamer curados consultan
  inventario actual y ofrecen opciones dentro del presupuesto; selecci�n y
  sustituciones por componente conservan elecciones y recalculan antes de
  aceptar. Venta de m�ltiples art�culos permite resolver RAM 8 GB y SSD 240 GB
  en secuencia. PostgreSQL consultado en lectura: hay marcas en `spare_parts.name`,
  no columna `brand`; no se alter� esquema ni se escribieron datos. 60 pruebas
  enfocadas aprobadas. Limitaci�n: perfiles predefinidos y compatibilidad f�sica
  pendiente de comprobaci�n de fichas. Evidencia en spec 11 y docs 14.
- Respuesta de capacidades (2026-10-13): consultas como �qu� funciones puedes
  realizar� ahora enumeran directamente las funciones implementadas y no caen
  en la FAQ de direcci�n/horarios simulados. Regresi�n incluida; 61 pruebas
  enfocadas, compileall y `git diff --check` correctos. Evidencia en Bloque 26.
- FAQ y datos operativos (2026-10-13): el RAG FAQ prioriza el tema consultado y
  cubre servicios, ubicaci�n, horario, cotizaciones, pagos, garant�as, log�stica
  y compras. Se eliminaron direcci�n/horarios de prueba del contexto: la respuesta
  aclara que no hay datos confirmados. 63 pruebas enfocadas, compileall y
  `git diff --check` correctos; limitaci�n real: sin ubicaci�n/horario/medios de
  pago confirmados. Evidencia: Bloque 27.
- Selecci�n de armado (2026-10-13): ahora se extraen n�meros de respuestas
  conversacionales como �elijo la 3� y �quiero la opci�n 2�, adem�s de ordinales
  y nombres de perfil. Prueba de flujo completo confirma la tercera opci�n.
  Validaci�n: 12 workflows, compileall y diff-check correctos. Evidencia: Bloque 28.
- Bienvenida general del chat (2026-10-13): reemplazado el saludo que asum�a una
  aver�a por una bienvenida que resume soporte, compras/cotizaciones, armado,
  garant�as y log�stica; actualizado React, Streamlit y chat est�tico. No se
  ejecutaron pruebas por ser un cambio de texto/UI.
- Actualizaci�n de FAQ de tienda (2026-10-13): a solicitud del usuario se
  a�adieron direcci�n ficticia en San Borja y horario peruano al RAG, marcados
  internamente como datos de demostraci�n para sustituir antes de producci�n.
  La FAQ los recupera para ubicaci�n/horario; retiro no se confunde con recepci�n.
  14 pruebas FAQ/workflows, compileall y diff-check aprobados. Sin escrituras BD.
  Evidencia: spec 14 y docs 17.
- FAQ comercial ampliada (2026-10-13): formas de pago ficticias (Yape, Plin,
  transferencia, Visa/Mastercard y efectivo), proceso paso a paso, tarifas base
  alineadas con settings y garant�a de 3 meses para venta/armado tras log�stica.
  El chat solo crea pago PENDING; no procesa pagos ni comparte cuentas/QR.
  15 pruebas FAQ/workflows, compileall y diff-check correctos. Evidencia: spec 14,
  docs 17. Valores de ubicaci�n, horario y medios de pago son de demostraci�n.
- Mis Tickets para cliente (2026-10-13): portal carga desde `/api/customer/tickets`
  autenticado; API filtra estrictamente por customer_id de sesi�n y devuelve estado,
  datos y �ltima cotizaci�n. UI conserva tarjetas/filtros/b�squeda y elimina aprobar/
  revisar/admin para ser solo lectura. Build Vite aprobado. Sin consultas ni escrituras
  PostgreSQL. Evidencia: spec 15, docs 18.
- Registro con sesión (2026-10-13): `POST /auth/registro` emite la misma cookie `techfix_session` que `/login`; un 409/422 no la emite. Corrige que tras registrarse "Mis Tickets" mostrara "Tu sesión terminó" (caso CN-02 de la caja negra del frontend). 2 pruebas nuevas en `tests/test_accounts_api.py`; pruebas de cuentas, sesión y chat aprobadas (72). Limitación: las pruebas RAG que llaman a Groq fallan sin red/clave y no dependen de este cambio.
- Seed de inventario (2026-10-13): precios de referencia en PEN ajustados con cat?logos peruanos; RAM y almacenamiento compactados para retirar filas redundantes y SKU duplicados entre bloques. Filas: 438 ? 310; 310 c?digos ?nicos y sin duplicados exactos de nombre/categor?a. Limitaci?n: ambos `ON CONFLICT (code) DO NOTHING` no actualizan cat?logo ya sembrado; no se ejecut? SQL ni se toc? PostgreSQL. Evidencia: spec 16, docs 19.
- Separación del frontend (2026-10-20): `landing/` pasa al repositorio TechFixAI-frontend (con su historial, sin archivos .env) y este repositorio se renombra a TechFixAI-backend. Los README de la raíz, cuentas y chat apuntan al repo del frontend. Limitación: Vercel debe reconectarse a TechFixAI-frontend antes de fusionar este cambio; las ramas con cambios en `landing/` sin integrar deben llevarlos al repo nuevo.
