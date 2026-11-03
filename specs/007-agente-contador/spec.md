# Feature Specification: Agente contador común a Orquestador, Jerárquico y Descentralizado

**Feature ID**: `007-agente-contador-compartido`  
**Working Branch**: `descentralizado-sprint2` (sin crear ni cambiar de rama)  
**Created**: 2026-11-03  
**Status**: Draft — pendiente de tres decisiones funcionales  
**Input**: User description: Integrar el agente contador como capacidad común de Orquestador, Jerárquico y Descentralizado reutilizando las funcionalidades de asientos contables y compras a proveedores. En esta etapa solo se define la especificación, sin implementar código ni inventar reglas contables. Dejar pendientes los usuarios autorizados, los eventos contables y la modalidad de propuesta o registro.

## Scope and Existing Capabilities

Esta funcionalidad define una capacidad contable compartida por Orquestador, Jerárquico y Descentralizado para atender solicitudes con contexto operativo verificable y comunicar sus resultados o limitaciones. Cada patrón la integra en su propio flujo bajo los mismos controles contables. No define un segundo libro contable ni otro sistema de compras.

- [003 — Asientos contables](../003-asientos-contables/spec.md) es la autoridad para registro, consulta, categorías, validación de líneas balanceadas, moneda PEN, responsable autenticado, idempotencia, auditoría y reversión. Su creación persiste un asiento confirmado; no dispone de un estado de propuesta pendiente de aprobación.
- [006 — Compras a proveedores](../006-registro-compras-proveedores/spec.md) es la autoridad para proveedores, comprobantes, líneas de costo, métodos/estados de pago y recepciones. Registrar una compra no incrementa inventario; una recepción confirmada lo incrementa una sola vez. Su FR-015 mantiene el asiento manual e independiente, sin contabilización automática.
- Cada patrón conserva sus contratos, identidad y rutas actuales. Descentralizado conserva además sus nueve roles existentes, ownership, transferencias, revisiones, locks, recuperación e identificadores persistidos.
- La cotización propuesta, su aceptación, una orden de pago pendiente y una solicitud de reembolso son hechos distintos. Ninguno acredita por sí mismo cobro, entrega, servicio ejecutado o devolución de dinero.
- El registro administrativo de compras de 006 y el Purchasing consultivo del grafo son capacidades diferentes; la presencia de la API administrativa no implica que el agente Purchasing pueda ejecutarla o que haya una transferencia contable habilitada.

Esta especificación no modifica las especificaciones 003 o 006. No habilita eventos automáticos ni amplía permisos administrativos por inferencia.

## Clarifications — Pending Decisions

No hay respuestas aprobadas para las siguientes preguntas. Se conservan abiertas por instrucción del solicitante; no se adoptan valores predeterminados.

- **Q-001 — Usuarios autorizados**: [NEEDS CLARIFICATION: ¿Quién puede usar el agente contador en cada patrón y para qué operaciones: consultar, solicitar una propuesta, revisarla y eventualmente registrar? ¿Cómo se relaciona ese acceso con el chat actual para clientes y con las operaciones contables y de compras reservadas a ADMIN?] El acceso al agente no debe otorgar acceso adicional a las capacidades protegidas de 003 o 006.
- **Q-002 — Eventos contables**: [NEEDS CLARIFICATION: ¿Qué eventos verificables de ventas, cobros, compras, recepciones, pagos a proveedores, reembolsos o correcciones pueden originar una propuesta o un asiento, en qué momento y con qué evidencia?] Debe confirmarse expresamente el criterio de reconocimiento; la lista de ejemplos no constituye una lista aprobada de disparadores. Cualquier decisión futura debe resolver su compatibilidad con FR-015 de 006 antes de habilitar efectos automáticos.
- **Q-003 — Modalidad y confirmación**: [NEEDS CLARIFICATION: ¿El agente solo prepara propuestas para revisión humana o también puede solicitar su registro mediante la capacidad existente? Si puede registrar, ¿quién confirma, en qué momento y con qué alcance?] La respuesta debe definir la aprobación, vigencia y tratamiento de reintentos. Una propuesta del agente no se guardará como un asiento CONFIRMED para simular un borrador.

Las historias y criterios condicionados a estas decisiones no habilitan implementación mientras sigan abiertos sus requisitos de autorización, evento o modalidad. No se necesita resolver esas preguntas para conservar este borrador de especificación.

## User Scenarios & Testing

### User Story 1 — Atender una solicitud contable con contexto verificable (Priority: P1)

Como persona autorizada según Q-001, quiero que el patrón seleccionado derive mi solicitud al agente contador conservando mi identidad y las referencias necesarias, para comprender qué operación se está revisando y qué información falta.

**Why this priority**: Evita que una conversación o transferencia se convierta en una autorización implícita o en evidencia de una operación económica.

**Independent Test**: Una vez resuelta Q-001, solicitar atención contable con una referencia válida y repetir con sesión inválida, referencia ajena y datos incompletos; verificar la información mostrada y la ausencia de cambios comerciales o contables no autorizados.

**Acceptance Scenarios**:

1. **Given** una sesión y una operación autorizadas según Q-001, **When** el patrón deriva la solicitud al contador, **Then** conserva la identidad autenticada y las referencias verificadas sin permitir que el mensaje cambie el propietario o responsable.
2. **Given** una referencia a un registro ajeno o no accesible para esa sesión, **When** se solicita su análisis, **Then** no se expone el registro ni se utiliza su contenido para una operación contable.
3. **Given** faltan referencias, evidencia o datos contables aprobados, **When** se analiza la solicitud, **Then** se enumeran los datos faltantes sin inventar cuentas, importes, fechas ni impuestos.
4. **Given** Q-001, Q-002 o Q-003 siguen abiertas, **When** se revisa el alcance de la integración, **Then** ninguna decisión pendiente se interpreta como un permiso o regla contable ya aprobados.

### User Story 2 — Presentar el resultado contable permitido (Priority: P1)

Como persona autorizada según Q-001, quiero distinguir la evidencia de origen, una propuesta y un asiento confirmado, para poder revisar el resultado permitido por Q-002 y Q-003 sin confundirlo con una cotización comercial.

**Why this priority**: Un resultado contable debe ser trazable a hechos y reglas aprobadas, y debe reflejar si existe o no un registro confirmado.

**Independent Test**: Tras resolver Q-001 a Q-003 y aprobar las reglas aplicables al caso, utilizar una operación verificable y comprobar su procedencia, información disponible, validación y resultado. Repetir con una cotización o pago pendiente y verificar que no se presentan como cobro o venta reconocida sin una regla aprobada.

**Acceptance Scenarios**:

1. **Given** un evento autorizado por Q-002 y evidencia suficiente, **When** se prepara el resultado permitido por Q-003, **Then** se identifican su origen y los datos utilizados, separando hechos verificados de información pendiente.
2. **Given** Q-003 establece solo propuestas, **When** se presenta una propuesta, **Then** se identifica como no registrada, no recibe correlativo de asiento confirmado y no modifica el libro contable.
3. **Given** una cotización aceptada, un pago PENDING o un reembolso REQUESTED, **When** se revisa su alcance económico, **Then** no se afirma que hubo cobro, entrega, prestación o reembolso ejecutado por ese solo estado.
4. **Given** no hay regla aprobada para las cuentas, categoría, tratamiento de importes o fecha aplicables, **When** se solicita una propuesta completa, **Then** se informa el bloqueo y no se completa usando supuestos del modelo.

### User Story 3 — Registrar y recuperar el resultado si se autoriza (Priority: P2, conditional)

Esta historia solo aplica si Q-003 autoriza registro. No forma parte de una modalidad limitada a propuestas.

Como persona con autorización efectiva para registrar según 003 y la decisión Q-001, quiero que el resultado confirmado utilice el registro contable existente, para conservar sus controles y recuperar una operación sin generar duplicados.

**Why this priority**: Evita crear un libro paralelo, eludir la aprobación o anunciar registros que no existen.

**Independent Test**: Si se habilita registro, confirmar una operación autorizada utilizando la capacidad existente y reintentar después de una respuesta perdida; comprobar que el resultado corresponde al registro real y que no se crea otro asiento para la misma operación lógica.

**Acceptance Scenarios**:

1. **Given** Q-003 permite registro y existe autorización y confirmación vigentes, **When** se solicita registrar, **Then** se reutiliza 003 con su validación, responsable auténtico e idempotencia, sin suplantar un ADMIN.
2. **Given** el servicio rechaza los datos o no confirma la persistencia, **When** el agente responde, **Then** no anuncia un asiento confirmado ni inventa su correlativo.
3. **Given** el registro se confirmó pero su respuesta se perdió, **When** se reintenta o recupera la misma operación, **Then** se identifica el asiento existente sin duplicar el efecto ni reutilizar una aprobación para contenido diferente.
4. **Given** una propuesta cambió o cambió su fuente antes de la confirmación, **When** se intenta registrar la versión anterior, **Then** se solicita revisión de la versión vigente y no se registra silenciosamente otra operación.
5. **Given** se requiere corregir un asiento confirmado, **When** se plantea una corrección, **Then** se mantienen las restricciones de 003: no editar ni borrar el historial; su mecanismo de reversión solo puede usarse con la autorización exigida.

### Edge Cases

- La solicitud llega mediante handoff, pero la persona no tiene acceso al registro de origen o a la operación contable.
- Un mensaje intenta reemplazar el responsable o afirmar que el usuario es ADMIN.
- Se registró una compra, pero aún no fue recibida; una recepción no implica pago y un estado de pago no implica recepción.
- Una compra incluye costos, descuentos o impuestos documentados: se conservan los valores de origen sin inferir una clasificación tributaria ni una tasa.
- El mismo caso se solicita desde dos conversaciones, se reintenta o llega por rutas distintas; si se permite registrar, no debe producir un efecto contable duplicado.
- El precio de venta difiere del costo histórico de compra: ninguno se sustituye por el otro sin una regla aprobada.
- La propuesta o su evidencia cambia después de una revisión; cualquier eventual confirmación debe referirse al contenido vigente.
- Se cancela o cambia el registro de origen, o se solicita revisar un asiento ya revertido; se informa el conflicto sin borrar historial ni ejecutar una compensación automática.
- Un fallo impide consultar la fuente o conocer el resultado del registro; se comunica la incertidumbre y se conserva la posibilidad de reconciliación.
- La integración contable falla: los flujos existentes de los nueve roles no deben perder su estado, sus permisos ni cambiar sus efectos comerciales.

## Requirements

### Functional Requirements

- **FR-001**: Los tres patrones deben poder integrar la misma capacidad del agente contador dentro del alcance que se apruebe en Q-001, Q-002 y Q-003; esta especificación no asigna permisos, eventos ni capacidad de registro por defecto.
- **FR-002**: La identidad y el responsable deben proceder de la sesión autenticada. Un mensaje, handoff o resultado del agente no puede conceder permisos ni seleccionar otro actor para ejecutar una operación protegida.
- **FR-003**: El acceso a cada fuente y operación debe respetar sus permisos vigentes. La integración no puede eludir las restricciones ADMIN de 003 o 006 para facilitar el acceso desde el chat.
- **FR-004**: El agente debe distinguir los estados comerciales y económicos disponibles, así como hechos verificados, datos faltantes, propuestas y registros confirmados. No debe confundir aceptación de cotización con cobro o reconocimiento de una venta.
- **FR-005**: Toda propuesta o eventual registro debe identificar sus referencias de origen y los datos utilizados. La evidencia y las reglas aprobadas deben permitir revisar el resultado sin depender únicamente del texto conversacional.
- **FR-006**: El agente no debe inventar cuentas, denominaciones, categorías, fechas, importes, impuestos, tasas, reglas tributarias, valoración de inventario ni criterios de reconocimiento. Cuando falten datos o reglas, debe indicar qué falta.
- **FR-007**: Se deben reutilizar las capacidades y contratos existentes de 003 y 006. No se deben duplicar sus APIs, servicios, repositorios, libro contable, registros de compras ni migraciones.
- **FR-008**: Si se permite preparar propuestas completas, deben respetar las validaciones existentes de 003 sobre exactitud monetaria en PEN, líneas y balance. Una propuesta incompleta o no balanceada no debe presentarse como lista para registrar.
- **FR-009**: Si Q-003 limita el agente a propuestas, ninguna interacción con él debe crear, revertir ni confirmar asientos. La propuesta debe distinguirse del registro confirmado y no utilizar el registro de 003 como almacén de borradores.
- **FR-010**: Si Q-003 habilita registro, se deben reutilizar las capacidades de 003, con autorización vigente, aprobación vinculada al contenido, validación, responsable autenticado, idempotencia y confirmación real antes de anunciar éxito.
- **FR-011**: Si se habilita registro, los reintentos, recuperación y solicitudes equivalentes desde varias conversaciones deben conservar la identificación de la operación lógica y evitar duplicados. La integración no debe suponer que una nueva clave o conversación convierte el mismo hecho en otra operación.
- **FR-012**: No se deben activar disparadores automáticos a partir de compras, recepciones, estados de pago, cotizaciones o reembolsos mientras Q-002 y Q-003 no están aprobadas. Se conserva la independencia contable exigida por FR-015 de 006.
- **FR-013**: La integración debe preservar rutas, contratos y efectos actuales de cada patrón. En Descentralizado debe preservar además los nueve roles existentes, identificadores persistidos, compatibilidad de nombres, handoffs, revisiones de propuestas comerciales, ownership, locks y recuperación. No debe añadir efectos de compra, cobro, stock o reembolso a sus operaciones actuales.
- **FR-014**: Los resultados y trazas deben permitir revisar la procedencia y el estado de una operación sin registrar credenciales, mensajes completos ni textos de excepciones técnicas.
- **FR-015**: Esta etapa entrega únicamente la especificación. No incluye código, rutas nuevas, migraciones, cambios en el frontend ni modificaciones a las especificaciones de referencia.

### Requisitos compartidos y tareas de integración por patrón

Los FR-001 a FR-012 y FR-014 son requisitos compartidos. FR-013 exige preservar el comportamiento de cada patrón. Ninguna integración crea otra API contable, servicio, repositorio o migración: se reutilizan las capacidades de 003 y los datos de 006 bajo sus permisos vigentes. Las tareas siguientes son futuras y están condicionadas por Q-001 a Q-003.

| Patrón | Tareas específicas | Comprobación de compatibilidad |
| --- | --- | --- |
| Orquestador | Conectar su enrutamiento y contexto a la capacidad compartida y devolver el resultado por el contrato de chat existente. | Conservar sus rutas y funciones, incluido reembolso, sin convertirlas en disparadores contables por defecto. |
| Jerárquico | Conectar su jerarquía de supervisión y estado a la misma capacidad. | Conservar delegaciones, estado y contratos; el enrutamiento no concede permisos administrativos. |
| Descentralizado | Conectar grafo, estado compartido y handoffs a la misma capacidad; definir su participación en el grafo tras resolver Q-001 a Q-003. | Conservar los nueve roles actuales, alias e identificadores persistidos, revisiones, ownership, locks y recuperación; sin nodos duplicados por compatibilidad. |

En los tres patrones, las futuras pruebas deben cubrir autorización, identidad, fuentes, propuesta o resultado informativo y, solo si se aprueba, registro y reintentos mediante 003. Una compra de 006 no crea automáticamente un asiento según FR-015; cambiarlo requiere decisión expresa y actualización de la especificación de origen.

### Key Entities

Entidades conceptuales; no son tablas nuevas ni un diseño de persistencia.

- **Solicitud contable**: petición con identidad autenticada, finalidad y referencias cuya autorización depende de Q-001.
- **Evidencia de origen**: datos verificables de una operación existente; conserva su tipo, identificador, estado y contexto temporal disponible.
- **Propuesta contable**: resultado no registrado y sujeto a reglas aprobadas, cuando la modalidad seleccionada lo permita; no equivale a una cotización comercial ni a un asiento confirmado.
- **Asiento existente**: registro de 003, reutilizado únicamente bajo sus controles y si Q-003 permite la operación.
- **Revisión/confirmación**: decisión de una persona autorizada vinculada al contenido correspondiente; quién la realiza y si habilita registro dependen de Q-001 y Q-003.

## Success Criteria

### Measurable Outcomes

Criterios para una futura aceptación; no representan pruebas ejecutadas. Los casos dependientes de Q-001 a Q-003 solo se concretarán después de aprobar esas decisiones y las reglas contables necesarias.

- **SC-001**: El 100 % de los casos de aceptación identifica si el resultado es información, propuesta no registrada o asiento confirmado, sin presentar una cotización o pago pendiente como un cobro.
- **SC-002**: El 100 % de las referencias ajenas o no autorizadas de la matriz aprobada en Q-001 se rechaza sin exponer información protegida ni producir escrituras.
- **SC-003**: El 100 % de los casos con datos o reglas faltantes informa el faltante y evita inventar cuentas, tasas, importes o confirmaciones de persistencia.
- **SC-004**: Si se aprueba modalidad de propuestas, el 100 % de sus casos de aceptación deja intactos los asientos y operaciones comerciales existentes.
- **SC-005**: Si se permite registrar, cada operación lógica sometida a reintentos o recuperación produce como máximo un asiento confirmado y conserva la identidad y referencias autorizadas.
- **SC-006**: La regresión de cada patrón conserva su enrutamiento, contratos y efectos previos; en Descentralizado conserva además los nueve roles existentes, identificadores, rutas comerciales, ownership y opciones de escritura.
- **SC-007**: La futura implementación reutiliza 003 y 006 sin añadir APIs, servicios o migraciones que dupliquen sus responsabilidades.

## Dependencies and Constraints

- [Especificación contable 003](../003-asientos-contables/spec.md), [modelo existente](../003-asientos-contables/data-model.md) y [contrato vigente](../003-asientos-contables/contracts/accounting.openapi.yaml).
- [Especificación de compras 006](../006-registro-compras-proveedores/spec.md), [modelo existente](../006-registro-compras-proveedores/data-model.md) y [contrato vigente](../006-registro-compras-proveedores/contracts/purchases.openapi.yaml).
- Capacidades actuales: `AccountingService`, `AccountingRepositoryAdapter`, `SupplierPurchaseService`, `SupplierPurchaseRepositoryAdapter` y composición autenticada del backend. Su reutilización no concede permisos al agente ni obliga a duplicar una API mediante otra ruta.
- Grafos, estado y enrutamiento propios de Orquestador, Jerárquico y Descentralizado. El estado compartido, ownership y recuperación de Descentralizado deben mantenerse; los mecanismos técnicos quedan para la planificación posterior.
- Decisiones Q-001, Q-002 y Q-003, además de los datos y reglas de negocio necesarios para cualquier caso contable concreto. No se presume un plan de cuentas ni un criterio tributario configurado.
- El alcance de 003 sigue siendo registro interno en PEN, sin certificación tributaria ni generación o presentación PLE. Se conserva el historial confirmado y su mecanismo de corrección existente.

## Out of Scope

- Implementar código o ejecutar migraciones en esta etapa.
- Duplicar el libro contable, APIs, servicios, tablas o migraciones de 003 y 006.
- Definir cuentas, impuestos, tasas, criterios de reconocimiento o valoración de inventario sin aprobación del equipo.
- Automatizar asientos o ampliar permisos mientras las preguntas pendientes no tengan respuesta aprobada.
- Cambiar las reglas de compras, ventas, pagos, inventario, reembolsos o el comportamiento existente de cualquiera de los tres patrones.
- Modificar frontend, `memory.md`, documentación general, planes o tareas de implementación.
