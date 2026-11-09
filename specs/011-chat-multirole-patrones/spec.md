# Feature Specification: Chat multirol coherente para los tres patrones

**Feature Branch**: `011-chat-multirole-patrones`
**Created**: 2026-11-09
**Status**: Draft
**Input**: Incorporar chat de texto y voz para clientes y ADMIN; compartir capacidades, políticas, conocimiento y perfiles reales de modelo en los tres patrones; ajustar los flujos al modelo comercial vigente y reparar inconsistencias de composición provenientes del merge.

## Clarifications

### Session 2026-11-09

- Q: ¿El ADMIN puede confirmar una propuesta diciendo claramente “confirmo” por voz, además de escribirlo, o prefieres exigir otra forma? → A: Aceptar confirmación explícita por voz o texto, solo si es inequívoca y pertenece a la propuesta pendiente del mismo ADMIN.
- Q: Si Render reinicia o atiende la confirmación en otra instancia, ¿qué debe pasar con una propuesta ADMIN pendiente? → A: Descartarla y pedir crearla de nuevo.

## User Scenarios & Testing

### User Story 1 - Atención coherente al cliente (Priority: P1)

Un cliente autenticado consulta por texto o voz y puede recibir orientación, pedir servicio técnico, consultar productos, preparar una cotización, revisar sus tickets, consultar garantía o logística y solicitar un reembolso pendiente. Los tres patrones mantienen su topología, pero aplican las mismas reglas comerciales, herramientas, fuentes y resultados. Los tickets se reservan para los casos que requieren seguimiento de servicio; la venta directa y el armado de PC se manejan como cotizaciones sin ticket.

**Why this priority**: El cliente es el flujo existente y sirve como base segura para comparar las topologías antes de habilitar operaciones administrativas.

**Independent Test**: Ejecutar escenarios equivalentes por chat de texto en cada patrón y comparar resultado normalizado, registros generados, ausencia de escrituras no autorizadas y acceso a datos propios.

**Acceptance Scenarios**:

1. **Given** un cliente autenticado, **When** consulta una guía o un dato institucional, **Then** los tres patrones responden con la evidencia común disponible y se abstienen si no existe evidencia suficiente.
2. **Given** una solicitud de reparación o soporte que requiere seguimiento, **When** el cliente aporta la información necesaria, **Then** se crea o actualiza un ticket de servicio asociado al cliente autenticado.
3. **Given** una compra de productos o un armado de PC, **When** se prepara una propuesta, **Then** se registra o presenta una cotización de venta sin crear un ticket de reparación.
4. **Given** una cotización de venta pendiente, **When** el cliente la acepta, **Then** la cotización se vincula al cliente, se conserva la reserva y el pago queda pendiente según el flujo existente; no se afirma que se recibió el pago.
5. **Given** un cliente que consulta tickets, cotizaciones, pagos o garantías, **When** proporciona referencias en el mensaje, **Then** cada operación vuelve a validar propiedad contra la sesión y no revela registros de otro cliente.
6. **Given** una solicitud de reembolso, **When** los datos y propiedad son válidos, **Then** solo se registra una solicitud pendiente de resolución manual, sin transferir dinero.

### User Story 2 - Operar el sistema como ADMIN por texto (Priority: P1)

Una persona ADMIN autenticada consulta y administra por lenguaje natural los recursos administrativos que ya tienen operaciones disponibles en el backend, como clientes, tickets, inventario, proveedores, compras, órdenes de compra, cotizaciones de venta y contabilidad.

**Why this priority**: Permite automatizar tareas del taller con los casos de uso ya expuestos, manteniendo separado el trabajo del cliente.

**Independent Test**: En una sesión ADMIN, realizar consultas de lectura y proponer una escritura; verificar rol, actor, resumen de confirmación y resultado final en los recursos existentes.

**Acceptance Scenarios**:

1. **Given** una sesión ADMIN, **When** pregunta por un recurso permitido, **Then** el asistente consulta los datos vigentes en la fuente operativa correspondiente y responde sin inventar valores.
2. **Given** una sesión ADMIN, **When** solicita una escritura válida, **Then** el asistente presenta un resumen de la operación y no cambia datos todavía.
3. **Given** una operación pendiente, **When** el mismo ADMIN confirma explícitamente en la misma conversación, **Then** el backend vuelve a validar los datos y ejecuta la operación una sola vez, atribuyéndola al ADMIN autenticado.
4. **Given** una operación pendiente, **When** el ADMIN corrige datos, pregunta algo distinto, cancela o confirma de forma ambigua, **Then** no se ejecuta la operación anterior y el asistente aclara el siguiente paso.
5. **Given** una cuenta CUSTOMER o TECHNICIAN, **When** intenta utilizar el chat o herramientas administrativas, **Then** el backend deniega el acceso sin ejecutar herramientas administrativas.

### User Story 3 - Usar voz con aislamiento de rol (Priority: P1)

Una persona cliente o ADMIN dicta una solicitud desde su experiencia de voz autenticada. La transcripción se procesa con las mismas capacidades y restricciones de su rol. La voz no concede permisos ni confirma automáticamente una escritura.

**Why this priority**: Lleva las operaciones conversacionales existentes a voz sin crear una vía de autorización distinta.

**Independent Test**: En sesiones de cliente y ADMIN, enviar audio válido para una consulta y para una escritura; comparar el rol aplicado con el de texto y confirmar que la escritura espera confirmación explícita.

**Acceptance Scenarios**:

1. **Given** un cliente autenticado, **When** envía audio, **Then** se transcribe y ejecuta únicamente el flujo de cliente.
2. **Given** un ADMIN autenticado, **When** envía audio, **Then** se transcribe y ejecuta únicamente el flujo de ADMIN.
3. **Given** audio o transcripción que solicita una escritura, **When** la operación requiere confirmación, **Then** se entrega una propuesta y se espera un turno posterior de confirmación explícita por voz o texto; la frase hablada debe identificar inequívocamente la confirmación y pertenecer a la misma sesión, conversación y propuesta pendiente.
4. **Given** una sesión expirada o un rol insuficiente, **When** se solicita procesamiento de audio, **Then** la petición se rechaza antes de ejecutar capacidades y no expone la transcripción a otra conversación.

### User Story 4 - Comparar los tres patrones con los mismos contratos (Priority: P1)

El equipo ejecuta los mismos escenarios de negocio y seguridad sobre Jerárquico, Orquestador y Descentralizado. Puede variar el enrutamiento interno, pero no el contrato funcional, la fuente de verdad, el perfil real de modelo ni las políticas por rol.

**Why this priority**: La comparación académica solo es válida si mide topologías y no diferencias ocultas de herramientas o modelos.

**Independent Test**: Ejecutar la matriz de contratos con modelos y repositorios falsos idénticos; comprobar resultados, escrituras, permisos, fuentes y configuración real de modelo.

**Acceptance Scenarios**:

1. **Given** el mismo escenario cliente o ADMIN, **When** se ejecuta en cada patrón, **Then** produce el mismo resultado normalizado y los mismos efectos de negocio.
2. **Given** los tres patrones inicializados, **When** se inspecciona su configuración efectiva, **Then** usan el mismo proveedor, modelo, temperatura y política base configurados.
3. **Given** una consulta factual, **When** cualquiera de los patrones recupera conocimiento, **Then** recibe pasajes del corpus común con la misma procedencia, nivel de confianza y regla de abstención.
4. **Given** una entrada adversarial o una herramienta con argumentos no válidos, **When** cualquiera de los patrones procesa la solicitud, **Then** conserva las mismas restricciones y no ejecuta efectos de negocio.

## Edge Cases

- El rol cambia entre cliente y ADMIN en el mismo navegador; una conversación anterior no puede cambiar de propietario ni continuar bajo el rol nuevo.
- Un ADMIN dicta una orden de escritura, la sesión expira y luego vuelve a iniciar sesión; la operación pendiente no se ejecuta con la nueva sesión sin volver a validar actor y confirmación.
- Una confirmación puede referirse a una cotización, pero el precio, stock o estado cambió antes del commit; el backend debe volver a validar y presentar la nueva propuesta.
- Dos confirmaciones concurrentes para la misma propuesta deben generar como máximo una escritura.
- Si una propuesta pendiente se pierde por reinicio o porque otra instancia no posee esa conversación, no se ejecuta; el ADMIN debe formular y confirmar una nueva propuesta.
- Un “sí” ambiguo, audio que solo repita la solicitud o confirmación de otra propuesta no autoriza la escritura; una confirmación hablada inequívoca del mismo ADMIN sí puede hacerlo.
- La transcripción está vacía, es ambigua, excede límites o falla el proveedor; no se invoca ningún agente ni herramienta.
- El corpus común está ausente, desactualizado o no encuentra evidencia; los agentes no sustituyen la respuesta con conocimiento de memoria.
- Las herramientas administrativas existentes no cubren una acción solicitada; el asistente informa que no está disponible y no simula cambios.
- El caso PC_BUILD se cotiza sin ticket; un caso de reparación/soporte asociado se representa en un ticket distinto de servicio.

## Requirements

### Functional Requirements

- **FR-001**: El sistema MUST determinar el rol y la identidad únicamente desde la sesión autenticada; nunca desde texto, transcripción, argumentos del modelo o un identificador libre del cliente.
- **FR-002**: El sistema MUST ofrecer chat de texto y voz para CUSTOMER y ADMIN, con capacidades separadas según el rol resuelto en el backend.
- **FR-003**: El sistema MUST denegar operaciones ADMIN a CUSTOMER y TECHNICIAN, incluso cuando el modelo intente invocarlas o la solicitud se origine en voz.
- **FR-004**: Los patrones MUST conservar sus grafos/topologías independientes y usar contratos de capacidades, herramientas, políticas y errores compartidos para los flujos comunes.
- **FR-005**: Las operaciones de lectura MUST consultar la fuente operativa vigente y validar propiedad/alcance; el RAG no sustituye a la base de datos para stock, precios, clientes, pagos, estados o compras.
- **FR-006**: Cada escritura ADMIN MUST producir una propuesta con recurso, acción y valores afectados; solo una confirmación explícita por voz o texto del ADMIN autenticado en la conversación y propuesta vinculadas puede autorizar su ejecución.
- **FR-007**: El backend MUST volver a validar autorización, estado, importes, stock y datos de referencia al confirmar; conflictos, cambios o solicitudes ambiguas no ejecutan la escritura.
- **FR-008**: Cada escritura MUST ser idempotente frente a reintentos de la misma confirmación cuando exista una clave/operación repetible, y MUST guardar al usuario ADMIN autenticado como actor según el contrato de persistencia disponible. Las propuestas pendientes son temporales y no sobreviven al reinicio del proceso ni se comparten entre instancias.
- **FR-009**: Los agentes cliente MUST resolver al cliente comercial desde la sesión y solo acceder a sus propios registros. El ADMIN que registra una operación manual MUST permanecer separado de la persona/empresa atendida.
- **FR-010**: Los tickets MUST representar servicios que requieren seguimiento. La venta directa y el armado de PC MUST generar cotizaciones sin ticket de servicio.
- **FR-011**: La aceptación de una cotización de venta MUST conservar los estados separados de cotización, pago, reserva y pedido; no puede presentarse un pago pendiente como recibido.
- **FR-012**: Los tres patrones MUST usar el mismo manifiesto, corpus, metadatos, filtros, ranking y política de abstención del RAG. El corpus solicitado parte de `app/agents/jerarquico/knowledge_base`; documentos útiles de otras rutas se consolidan o excluyen mediante revisión, sin borrado ciego.
- **FR-013**: Los agentes MUST tratar documentos recuperados y mensajes como datos no confiables, no como instrucciones de sistema, y conservar procedencia para respuestas basadas en conocimiento.
- **FR-014**: Los tres patrones MUST ejecutar el mismo proveedor, modelo y parámetros de generación configurados; que las trazas reporten el mismo nombre no basta si el modelo efectivo difiere.
- **FR-015**: Los prompts MUST seguir una política común que define rol, objetivo, fuentes, límites, autoridad de herramientas, confirmación, abstención y manejo de errores; cada agente añade solo sus instrucciones de dominio.
- **FR-016**: El acceso por voz MUST aplicar autenticación y autorización antes de invocar transcripción o herramientas; sus límites y controles de disponibilidad existentes siguen vigentes.
- **FR-017**: Los casos de uso administrativos MUST limitarse a operaciones ya soportadas por las rutas/capacidades de backend; no se inventan endpoints ni datos de proveedores/precios que el sistema no posee.
- **FR-018**: La aplicación MUST iniciar de forma coherente los recursos necesarios para las rutas de chat publicadas y no dejar rutas de chat registradas pero inoperativas.
- **FR-019**: La matriz de contrato MUST incluir cliente y ADMIN, texto y voz, y los tres patrones; debe verificar resultados, side effects, aislamiento de roles, confirmación, modelo efectivo y recuperación RAG.
- **FR-020**: Las trazas MUST mantener metadatos suficientes para comparar patrón, escenario y perfil de modelo y MUST respetar `LANGSMITH_HIDE_INPUTS` y `LANGSMITH_HIDE_OUTPUTS`; cuando estén en `false`, LangSmith puede recibir el texto de entrada/salida para evaluación. En todos los modos MUST excluir credenciales, cookies, audio crudo y secretos de herramientas.
- **FR-021**: Cuando un especialista del patrón Descentralizado produzca una evaluación técnica para un ticket propio de servicio, el backend MUST persistirla en los campos de diagnóstico correspondientes del mismo ticket, validando el cliente autenticado. Una falla de persistencia MUST impedir que el flujo continúe hacia una cotización como si el diagnóstico estuviera guardado; las evaluaciones previas del otro especialista no deben borrarse.
- **FR-022**: `GET /api/customer/tickets` MUST incluir `diagnosis_type`, `hardware_diagnosis` y `software_diagnosis` para cada ticket devuelto. El backend MUST limitar los resultados al cliente comercial resuelto desde la sesión autenticada, sin aceptar un `customer_id` del request como autoridad.

### Key Entities

- **Principal autenticado**: cuenta cliente o ADMIN verificada por sesión; aporta identidad y rol confiables.
- **Conversación**: secuencia de turnos propiedad de una identidad y rol; no se comparte entre cliente y ADMIN.
- **Propuesta administrativa**: acción de escritura normalizada y pendiente, vinculada al ADMIN y a la conversación, que solo se ejecuta después de confirmación válida.
- **Capacidad de negocio**: operación tipada de lectura o escritura que aplica las mismas reglas a través de cada patrón.
- **Fuente de conocimiento**: documento Markdown registrado con área, confianza, audiencia, idioma, versión y procedencia.
- **Cotización de venta**: propuesta comercial con cliente, líneas, importe y estados; puede existir sin ticket, incluso para armado de PC.
- **Ticket de servicio**: caso asociado al cliente para reparación/soporte y seguimiento técnico, separado del actor que lo registra.

## Success Criteria

### Measurable Outcomes

- **SC-001**: En la matriz de escenarios, 100% de las operaciones CUSTOMER y ADMIN son aceptadas solo por el rol autorizado y 100% de intentos cruzados son denegados sin escrituras.
- **SC-002**: En pruebas de contrato, los tres patrones producen los mismos resultados normalizados y efectos de negocio para todos los escenarios comunes definidos.
- **SC-003**: Ninguna escritura ADMIN ocurre antes de una confirmación explícita; confirmaciones repetidas ejecutan como máximo una escritura.
- **SC-004**: El 100% de las respuestas basadas en RAG conserva fuente y nivel de confianza; sin evidencia suficiente, los patrones se abstienen.
- **SC-005**: El modelo y sus parámetros efectivos coinciden en los tres patrones en el 100% de escenarios de comparación.
- **SC-006**: Una cotización directa y una cotización PC_BUILD pueden persistirse, aceptarse y consultarse sin crear ticket; los flujos de reparación/soporte mantienen su ticket de servicio.
- **SC-007**: Fallas de audio, LLM, recuperación o almacenamiento no se presentan como operaciones completadas y no producen escrituras parciales no confirmadas.

## Assumptions

- La autenticación, roles `CUSTOMER`, `ADMIN` y `TECHNICIAN`, y cookies de sesión existentes se reutilizan.
- Se conservan las tres topologías LangGraph; se comparte su capa de capacidades en lugar de fusionar sus grafos.
- La experiencia frontend y sus cambios visuales quedan fuera de esta entrega backend; se mantienen contratos para que una especificación frontend posterior consuma las rutas.
- El chat ADMIN solo expone acciones que el backend ya soporta con autorización ADMIN. Funciones faltantes se responden como no disponibles hasta que tengan contrato propio.
- Toda escritura ADMIN, de bajo o alto riesgo, exige confirmación explícita según la decisión del usuario.
- La visibilidad del texto en LangSmith depende de `LANGSMITH_HIDE_INPUTS` y `LANGSMITH_HIDE_OUTPUTS`; su configuración `false` está permitida para evaluación, manteniendo fuera credenciales y bytes de audio.
- La confirmación PC_BUILD de esta feature establece cotización sin ticket; cualquier requisito de orden, entrega o garantía para ese flujo debe adaptarse a los recursos comerciales existentes y no crear un ticket ficticio.
- Se mantiene el esquema de conversaciones/checkpoints actual en memoria. Si se pierde una conversación/propuesta por reinicio o cambio de instancia, la confirmación no se ejecuta y el ADMIN debe volver a formular la operación.
- Las migraciones, si resultan necesarias para permitir cotizaciones `PC_BUILD` sin ticket, serán versionadas y aditivas; no se ejecutarán scripts de reconstrucción.
