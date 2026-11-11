# Feature Specification: Patrones multiagente coherentes y trazables

**Feature Branch**: `001-patrones-multiagente-coherentes`

**Created**: 2026-11-02

**Status**: Implementation complete (52 of 52 tasks); full regression suite passed.

**Input**: User description: Conservar los patrones jerárquico, orquestador y descentralizado para comparación académica en LangSmith; compartir herramientas, políticas y pruebas de contrato; unificar RAG; cubrir los flujos funcionales del patrón jerárquico; retirar componentes que no se usen; alinear el sistema con el esquema ampliado de `contexto/tablas postgres v2.sql` mediante cambios trazables.

## User Scenarios & Testing

### User Story 1 - Comparar patrones con las mismas capacidades (Priority: P1)

Un cliente puede seleccionar cualquiera de los tres patrones y completar los mismos flujos de atención soportados. Cada patrón conserva su estilo de coordinación para que el equipo pueda comparar su comportamiento, pero precios, inventario, políticas, permisos y resultados de negocio se mantienen coherentes.

**Why this priority**: La comparación académica solo es válida si las diferencias observadas provienen de la coordinación y no de herramientas, reglas o datos distintos.

**Independent Test**: Ejecutar el mismo conjunto de escenarios con cada patrón y comprobar que las respuestas y cambios de negocio coinciden, permitiendo diferencias en la secuencia interna de agentes.

**Acceptance Scenarios**:

1. **Given** una solicitud válida de reparación, **When** se procesa con cada patrón, **Then** todos usan los mismos datos de diagnóstico, inventario y tarifa, y respetan las mismas confirmaciones antes de guardar.
2. **Given** una consulta comercial o de armado de PC, **When** se procesa con cada patrón, **Then** catálogo, precios, disponibilidad, selección y total siguen las mismas reglas.
3. **Given** una conversación iniciada con un patrón, **When** el cliente envía otro turno, **Then** la conversación sigue ligada a ese patrón y la misma identidad autenticada.
4. **Given** una operación no soportada o datos insuficientes, **When** cualquier patrón recibe la solicitud, **Then** comunica la misma limitación sin inventar resultados ni completar operaciones parcialmente. Las compras externas quedan no disponibles hasta definir una fuente confiable de proveedor, artículo, precio y plazo.
5. **Given** ejecuciones comparativas del mismo escenario, **When** se invocan los tres patrones, **Then** usan el mismo perfil de modelo y parámetros por defecto, salvo que la evaluación registre explícitamente una variable experimental distinta.

### User Story 2 - Recibir respuestas fundamentadas en conocimiento común (Priority: P1)

Un cliente recibe orientación técnica o respuestas frecuentes basadas en el mismo conjunto de documentos aprobados, sin importar qué patrón coordina la conversación. El equipo puede identificar qué fuentes sustentaron la respuesta.

**Why this priority**: Hoy cada patrón recupera documentos de forma distinta, lo que impide comparar respuestas y facilita contradicciones.

**Independent Test**: Consultar casos con evidencia, casos sin evidencia y consultas ambiguas mediante los tres patrones; comparar pasajes recuperados, abstención y referencias de fuente.

**Acceptance Scenarios**:

1. **Given** una consulta cubierta por documentos aprobados, **When** cualquier patrón solicita conocimiento, **Then** recibe los mismos pasajes pertinentes y sus referencias de origen.
2. **Given** que no hay evidencia suficiente, **When** el agente responde, **Then** expresa la incertidumbre y no presenta como confirmado un diagnóstico, precio o compatibilidad.
3. **Given** una consulta de atención frecuente, **When** se recupera una respuesta institucional, **Then** los tres patrones usan la misma versión aprobada de esos datos.
4. **Given** un documento institucional marcado como demostrativo, **When** un cliente pregunta por dirección, horario, pagos o tarifas, **Then** el sistema conserva la marca de demostración y no presenta esos datos como información real verificada.

### User Story 3 - Completar los flujos de servicio y posventa aplicables (Priority: P1)

Un cliente puede continuar desde la recepción y clasificación hasta diagnóstico, consulta o selección de inventario, cotización, confirmación y operaciones posteriores que estén soportadas por los datos y servicios configurados. Esto incluye soporte de hardware y software, FAQ, ventas, armado de PC, consultas/reclamos de garantía, solicitudes de reembolso pendientes y logística documentada.

**Why this priority**: El patrón jerárquico contiene la cobertura de negocio más amplia y debe ser la referencia funcional para los tres patrones.

**Independent Test**: Recorrer cada flujo implementado desde el contrato de chat con dependencias externas simuladas y verificar las transiciones, escrituras y mensajes terminales.

**Acceptance Scenarios**:

1. **Given** una solicitud de soporte con información insuficiente, **When** se inicia el flujo, **Then** el sistema solicita aclaración antes de guardar un diagnóstico o presupuesto no sustentado.
2. **Given** un diagnóstico y repuestos identificados, **When** se consulta inventario, **Then** solo se muestran opciones del catálogo y la cotización requiere confirmación explícita antes de persistirse.
3. **Given** una venta o armado de PC, **When** el cliente elige artículos, **Then** los artículos, precios y cantidades corresponden al catálogo vigente y el sistema no afirma compatibilidad sin evidencia.
4. **Given** una consulta o reclamo de garantía, **When** se valida la póliza, **Then** se comprueba su relación con el cliente autenticado y se registra únicamente la transición permitida.
5. **Given** que una operación crea pago pendiente o preferencia logística, **When** se confirma el flujo, **Then** se indica con claridad que no implica pago recibido, reserva de stock, recepción ni entrega.
6. **Given** un cliente autenticado solicita un reembolso de un pago de su cuenta, **When** los datos de pago y monto son válidos, **Then** el sistema registra la solicitud como pendiente de revisión manual y no afirma que el dinero fue devuelto.

### User Story 4 - Actualizar el esquema sin perder trazabilidad (Priority: P1)

El equipo puede incorporar los campos y tablas que requieren los flujos utilizando como referencia el esquema ampliado acordado, con cambios registrados y repetibles. Los datos de prueba existentes se conservan salvo que una migración aprobada requiera una transformación explícita.

**Why this priority**: El SQL de referencia permite comparar el modelo pretendido con el repositorio, pero también contiene instrucciones que eliminarían tablas existentes.

**Independent Test**: Aplicar migraciones sobre una base de prueba con datos representativos; comprobar versión, integridad referencial y lectura/escritura de los flujos cubiertos.

**Acceptance Scenarios**:

1. **Given** una base de prueba con el esquema actual y registros, **When** se aplican las migraciones de la funcionalidad, **Then** se preservan los registros existentes y se registra qué versión de esquema quedó aplicada.
2. **Given** una migración ya aplicada, **When** se vuelve a ejecutar el mecanismo de migración, **Then** no se repiten ni duplican cambios.
3. **Given** un cambio de esquema que no pueda preservar datos automáticamente, **When** se prepara, **Then** la migración identifica la transformación requerida y no elimina información en silencio.

### User Story 5 - Comparar ejecuciones en LangSmith sin exponer datos (Priority: P2)

El equipo puede comparar los tres patrones por conversación, flujo, modelo y resultado, conservando trazas útiles sin registrar contenido sensible del cliente.

**Why this priority**: La comparación académica requiere trazabilidad común, pero los mensajes pueden incluir datos personales y direcciones.

**Independent Test**: Inspeccionar ejecuciones de los tres patrones y confirmar metadatos consistentes, correlación por conversación y ausencia de mensajes/secretos en trazas configuradas como redactadas.

**Acceptance Scenarios**:

1. **Given** ejecuciones del mismo escenario en patrones distintos, **When** se revisan en LangSmith, **Then** se distinguen por patrón y se correlacionan con el mismo caso de evaluación.
2. **Given** trazas con redacción habilitada, **When** se inspeccionan entradas, salidas y errores, **Then** no contienen credenciales ni texto sensible del cliente.
3. **Given** una revisión de limpieza, **When** se identifica un componente aparentemente obsoleto, **Then** se conserva si lo usa algún patrón, prueba o flujo de evaluación y solo se retira tras verificar que no tiene referencias activas.

### Edge Cases

- El producto solicitado no coincide con un artículo único del catálogo o la consulta devuelve varias alternativas.
- Un artículo existe, pero no tiene stock suficiente, precio positivo o datos de compatibilidad confiables.
- No se encuentran documentos relevantes o hay resultados de relevancia baja/contradictorios.
- El proveedor LLM, la base de datos o el índice de conocimiento no están disponibles.
- El usuario rechaza una cotización, envía una confirmación ambigua o cambia el alcance de la solicitud entre turnos.
- Una migración encuentra una versión de esquema inesperada o filas que no satisfacen las nuevas restricciones.
- Se reanuda una conversación en otra instancia de API o después de reiniciar el proceso.
- La consulta solicita compra externa; el sistema responde que aún no puede cotizar ni prometer costo o plazo porque falta una fuente confiable de proveedor, artículo, precio y plazo.

## Requirements

### Functional Requirements

- **FR-001**: El sistema MUST mantener disponibles los tres patrones para comparación académica y permitir distinguirlos en cada conversación y traza.
- **FR-002**: Los tres patrones MUST aplicar los mismos contratos de entrada/salida y las mismas reglas de negocio para cada capacidad compartida; su topología y secuencia de coordinación pueden diferir.
- **FR-003**: Las capacidades de consulta de catálogo, inventario, cálculo de cotización, autorización de escritura, ticket y consulta de conocimiento MUST tener resultados equivalentes entre patrones para entradas iguales.
- **FR-004**: Las respuestas MUST obtener precios y existencias del catálogo vigente y MUST usar cálculos monetarios exactos; un LLM no puede decidir el precio final ni confirmar stock.
- **FR-005**: El sistema MUST requerir confirmación explícita del cliente antes de guardar una cotización u operación que el flujo presente como sujeta a aprobación.
- **FR-006**: Las operaciones sobre tickets, pólizas y reclamos MUST validar el vínculo con la identidad autenticada del cliente.
- **FR-007**: Los flujos MUST distinguir claramente entre operación propuesta, registrada, pendiente de pago, pagada, reservada, recibida y entregada. No se puede afirmar que una etapa ocurrió si no hay registro que la confirme.
- **FR-008**: El patrón MUST soportar, según el flujo y datos existentes, atención/FAQ, soporte de hardware y software, venta de productos, armado de PC, inventario, cotizaciones, pagos pendientes, logística, consulta de garantía y reclamos.
- **FR-009**: Las recomendaciones técnicas MUST distinguir evidencia, hipótesis y compatibilidad confirmada; si la evidencia aprobada no basta, el sistema MUST abstenerse de afirmar una causa o compatibilidad.
- **FR-010**: Los tres patrones MUST consultar una interfaz común de recuperación sobre fuentes de conocimiento aprobadas, con referencias de origen y resultado reproducible para la misma consulta y versión de fuentes.
- **FR-011**: La ingesta MUST identificar documentos fuente, evitar duplicados en reingestas y permitir reconstruir qué versión de documentos generó el índice.
- **FR-011a**: La información institucional identificada como demostrativa MUST conservar esa marca y no presentarse como un dato real verificado del negocio.
- **FR-012**: El sistema MUST mantener `contexto/tablas postgres v2.sql` como script de reconstrucción del esquema `public` generado desde la base PostgreSQL vigente, sin filas. Su ejecución elimina y recrea los objetos exportados y solo se permite en una base destino reinicializable; una base existente con datos se actualiza mediante migraciones versionadas.
- **FR-013**: Todo cambio de base de datos MUST quedar en una migración versionada con descripción de propósito, objetos afectados y estrategia de preservación/transformación de datos.
- **FR-014**: El sistema MUST definir pruebas de contrato comunes que ejecuten los mismos escenarios contra los tres patrones y validen respuestas, efectos de negocio, permisos y errores equivalentes.
- **FR-015**: Las trazas MUST identificar patrón, caso, agente/herramienta, modelo y resultado de negocio sin registrar credenciales ni contenido sensible cuando la redacción esté habilitada.
- **FR-016**: El sistema MUST retirar código, herramientas o documentación duplicados solo cuando se compruebe que no se usan en la API, pruebas, scripts operativos ni comparación académica.
- **FR-017**: El sistema MUST informar que las compras a proveedores no están disponibles mientras no exista una relación de datos confiable entre proveedor, artículo, precio y plazo; los patrones MUST responder de forma equivalente.
- **FR-018**: El sistema MUST permitir registrar una solicitud de reembolso con estado inicial pendiente para un pago vinculado al cliente autenticado, sin aprobarla, procesarla ni afirmar que se transfirió dinero.
- **FR-019**: Los tres patrones MUST aplicar las mismas validaciones de elegibilidad, propiedad, monto y duplicidad para una solicitud de reembolso y devolver un resultado equivalente.
- **FR-020**: Los tres patrones MUST usar el mismo perfil de modelo y parámetros configurados durante una comparación, salvo que la evaluación documente explícitamente esa configuración como variable experimental.

### Key Entities

- **Patrón de ejecución**: estrategia de coordinación elegida para una conversación y sus metadatos de evaluación.
- **Conversación**: historial y estado de un cliente bajo un patrón fijo.
- **Artículo de catálogo**: producto/repuesto con código, precio, stock, estado y datos de categoría.
- **Ticket**: solicitud del cliente con tipo, estado, descripción y diagnóstico separado por tipo cuando aplique.
- **Cotización y detalle**: propuesta monetaria vinculada al ticket y a productos/cantidades con precios registrados.
- **Pago**: obligación asociada a una cotización que puede quedar pendiente; no equivale a confirmación de pago.
- **Registro logístico**: modalidad y estado de recepción/entrega asociados al ticket.
- **Póliza y reclamo de garantía**: cobertura asociada a cliente/venta/servicio y su evaluación.
- **Fuente de conocimiento**: documento aprobado y versión de fragmentos recuperables con referencia de origen.
- **Ejecución de evaluación**: caso de comparación común con patrón, resultado y referencia de traza.

## Success Criteria

### Measurable Outcomes

- **SC-001**: El 100% de los escenarios de contrato compartidos produce resultados equivalentes en estado de negocio y política en los tres patrones.
- **SC-002**: El 100% de las cotizaciones persistidas tiene total igual a la suma de líneas y mano de obra, y corresponde a la selección confirmada por el cliente.
- **SC-003**: El 100% de las respuestas técnicas de evaluación incluye referencias de evidencia cuando existen fuentes suficientes, y expresa abstención cuando no las hay.
- **SC-004**: La aplicación de una migración sobre una base de prueba representativa conserva el 100% de las filas preexistentes que no estén explícitamente sujetas a transformación aprobada.
- **SC-005**: En escenarios de pago, inventario y logística, ningún patrón reporta como completada una operación que solo está pendiente o no fue registrada.
- **SC-006**: Las trazas de evaluación permiten identificar patrón, flujo y herramientas para el 100% de las ejecuciones comparativas, sin incluir secretos configurados para redacción.
- **SC-007**: El inventario final de componentes permite identificar para cada módulo si está activo, compartido, exclusivo de un patrón, de evaluación o retirado.
- **SC-008**: El 100% de las solicitudes de reembolso registradas permanece pendiente hasta una resolución manual y pertenece al pago y cliente autenticados correspondientes.

## Assumptions

- Los tres patrones son requisito permanente para comparación académica; no se busca hacerlos converger en un solo grafo.
- El patrón jerárquico define la cobertura de negocio de referencia, mientras la selección de patrón conserva diferencias de coordinación medibles.
- `contexto/tablas postgres v2.sql` refleja la base local `multiagentedb` desde 2026-11-03; la base es la fuente de verdad. `sql/creacion_tablas_ingles_sin_inserciones.sql` es un bootstrap legado incompleto y no se usa para actualizar la base vigente.
- La base de datos configurada en `.env` es de prueba, según confirmó el usuario. Las credenciales y URL de conexión no deben imprimirse ni incluirse en trazas o documentación.
- Las modificaciones de esquema se registran con migraciones aditivas/versionadas y conservan datos por defecto.
- Los flujos de pago no integran una pasarela de cobro salvo que exista un proveedor configurado; `PENDING` no equivale a pago recibido.
- Las compras externas permanecen explícitamente no disponibles hasta aprobar el modelo de datos y la fuente de precios/plazos de proveedores.
- Las solicitudes de reembolso se registran para revisión manual; esta funcionalidad no ejecuta una transferencia ni decide aprobación.
- El inventario no se reserva ni descuenta automáticamente a menos que el flujo existente y el esquema lo soporten de manera explícita.
- El estado de conversación y los checkpointers permanecen en memoria durante esta etapa; hacerlos duraderos no forma parte del alcance confirmado.
- Los archivos actuales de `spec/` son documentación histórica; los artefactos nuevos de Spec Kit viven en `specs/`.

