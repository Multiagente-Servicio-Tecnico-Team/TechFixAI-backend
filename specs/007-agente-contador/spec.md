# Feature Specification: Asistente contable común para los tres patrones

**Feature ID**: 007-agente-contador-compartido
**Working Branch**: descentralizado-sprint2
**Created**: 2026-11-03
**Status**: Draft — alcance funcional definido; sin implementación
**Input**: Asistente conversacional exclusivo para ADMIN que guía operaciones manuales del registro contable 003 en Orquestador, Jerárquico y Descentralizado.

## Scope and Existing Capabilities

Esta funcionalidad ayuda a ADMIN a usar las operaciones contables existentes de [003 — Asientos contables](../003-asientos-contables/spec.md). No contabiliza eventos comerciales ni deriva datos contables de otras áreas. [001 — Patrones coherentes](../001-patrones-multiagente-coherentes/spec.md) exige el mismo contrato y reglas de negocio en los tres patrones, conservando su coordinación propia. El contador no actúa como supervisor global.

[006 — Compras a proveedores](../006-registro-compras-proveedores/spec.md) mantiene registro, pago y recepción como hechos operativos separados. Su FR-015 prohíbe crear asientos automáticamente al registrar una compra. Esta especificación no modifica 001, 003 ni 006.

## Clarifications — Decisions

### Session 2026-11-03

- Solo una sesión autenticada ADMIN puede usar el asistente para consultar, preparar datos, crear o solicitar reversión. CUSTOMER y TECHNICIAN no pueden consultar propuestas ni asientos.
- D1 del [research de 003](../003-asientos-contables/research.md) se mantiene: un ADMIN crea cada asiento a través de la API; 003 no deriva asientos desde pagos, cotizaciones, órdenes de compra, reembolsos ni agentes.
- ADMIN ingresa manualmente los datos y líneas. El asistente muestra una vista previa temporal y valida con las reglas deterministas de 003; no persiste borradores ni existe DRAFT.
- Sin confirmación explícita de ADMIN no se llama a la operación de creación. El flujo existente de 003 crea un asiento confirmado en una sola operación. El agente no decide ni confirma por su cuenta.

## User Scenarios & Testing

### User Story 1 — Consultar contabilidad (Priority: P1)

Como ADMIN, quiero consultar categorías, asientos y el detalle de un asiento desde cualquiera de los patrones para revisar los registros existentes sin cambiar sus datos.

**Independent Test**: Repetir las consultas con los tres patrones y comprobar que la autorización, filtros y resultados siguen el contrato de 003.

**Acceptance Scenarios**:

1. **Given** ADMIN autenticado, **When** pide categorías activas, **Then** recibe las categorías de 003, sin crear otras.
2. **Given** ADMIN autenticado, **When** lista asientos con filtros admitidos por 003 o consulta un detalle, **Then** recibe solo el resultado de la operación existente, incluido estado e historial disponibles.
3. **Given** CUSTOMER, TECHNICIAN o una sesión ausente, **When** intenta consultar categorías, asientos, detalles o vistas previas, **Then** el backend rechaza la operación sin exponer datos.

### User Story 2 — Preparar y confirmar un asiento manual (Priority: P1)

Como ADMIN, quiero ingresar fecha, concepto, detalle, categoría y líneas de cuenta con debe/haber, revisar una vista previa y confirmar expresamente antes de crear el asiento.

**Independent Test**: Ingresar datos válidos y luego incompletos o desbalanceados; comprobar que solo una confirmación válida llama a la creación de 003 y que el registro resultante queda confirmado.

**Acceptance Scenarios**:

1. **Given** ADMIN proporciona los campos y al menos dos líneas, **When** pide vista previa, **Then** el asistente muestra únicamente esos datos y los totales calculados con exactitud decimal, sin persistir un asiento.
2. **Given** falta fecha, concepto, detalle, categoría o una línea necesaria, **When** se valida, **Then** se solicita el dato faltante; no se inventan cuentas, importes, impuestos ni costos.
3. **Given** una línea sin importe positivo en exactamente un lado o totales debe/haber distintos, **When** se valida, **Then** la vista previa no se presenta como registrable y no se llama a escritura.
4. **Given** una vista previa válida pero no confirmada, **When** termina o se reanuda la conversación, **Then** no existe asiento persistido ni estado DRAFT; cualquier dato conversacional no sustituye la confirmación.
5. **Given** ADMIN confirma expresamente el contenido vigente, **When** el backend usa la creación de 003, **Then** el asiento queda CONFIRMED en una sola operación con responsable de la sesión, auditoría e idempotencia.
6. **Given** cambia cualquier dato después de la vista previa, **When** se intenta confirmar una versión anterior, **Then** se solicita nueva revisión y no se registra silenciosamente otro contenido.

### User Story 3 — Solicitar reversión (Priority: P2)

Como ADMIN, quiero revisar un asiento y solicitar su reversión con motivo para corregirlo mediante el mecanismo inmutable de 003.

**Independent Test**: Solicitar reversión de un asiento confirmado con motivo y repetirla; verificar resultado e idempotencia de 003, sin editar ni borrar el original.

**Acceptance Scenarios**:

1. **Given** ADMIN identifica un asiento confirmado y proporciona motivo, **When** confirma la reversión, **Then** se usa la operación existente de 003 y se muestra el vínculo entre original y asiento inverso.
2. **Given** falta motivo o el asiento no admite reversión, **When** se solicita, **Then** se explica el impedimento y no se modifica el registro.

### Edge Cases

- El texto del chat no puede atribuir otro rol ni elegir otro responsable: el backend comprueba sesión y permisos.
- Una cotización, un pago pendiente, una compra, una recepción, un reembolso o un movimiento de inventario no alimenta líneas contables ni desencadena una escritura.
- Si 003 rechaza categoría, línea, balance, autorización o reversión, el asistente transmite el resultado sin afirmar un registro inexistente.
- Un reintento tras respuesta perdida conserva la clave y el contenido de la operación lógica según 003; no crea un segundo asiento.
- Si faltan datos ingresados por ADMIN, el asistente pregunta; no completa valores por RAG, catálogo, estimaciones o reglas tributarias inferidas.

## Requirements

### Functional Requirements

- **FR-001**: El backend debe permitir estas operaciones solo a ADMIN autenticado; CUSTOMER y TECHNICIAN no pueden consultar propuestas ni asientos. Responsable y auditoría provienen de la sesión, nunca del mensaje.
- **FR-002**: Orquestador, Jerárquico y Descentralizado deben ofrecer la misma capacidad y contrato contable, manteniendo su coordinación, grafo, estado y rutas de chat propios; el contador no es supervisor global.
- **FR-003**: El asistente debe reutilizar las operaciones de 003 para consultar categorías activas, listar y filtrar asientos, consultar detalles, crear un asiento confirmado y solicitar una reversión con motivo. No crea rutas ni servicios contables paralelos.
- **FR-004**: Para crear, ADMIN debe aportar fecha de operación, concepto, detalle, categoría válida y al menos dos líneas con código y denominación de cuenta e importe al debe o al haber.
- **FR-005**: La validación debe aplicar las reglas deterministas de 003: importe decimal positivo en exactamente un lado de cada línea y totales de debe/haber iguales. El asistente no decide cuentas ni importes.
- **FR-006**: Ante cualquier dato faltante o inválido, debe solicitar aclaración y no inventar cuentas, importes, impuestos, costos, fechas ni tratamientos tributarios.
- **FR-007**: La vista previa es temporal y contiene solo los datos ingresados por ADMIN y totales derivados de ellos. No es un asiento persistido, no recibe correlativo y no introduce estado DRAFT.
- **FR-008**: Solo tras confirmación explícita de ADMIN del contenido vigente puede el backend llamar a la creación existente de 003; el resultado queda CONFIRMED en una sola operación. El agente no registra ni confirma por sí solo.
- **FR-009**: Creación y reversión conservan autorización, validación, inmutabilidad, auditoría, atomicidad e idempotencia definidas en 003. Una reversión exige motivo y no edita ni elimina el asiento original.
- **FR-010**: No se derivan líneas ni asientos desde ventas, pagos, cotizaciones, compras, reembolsos o inventario. 006 conserva sus operaciones y su prohibición de contabilización automática.
- **FR-011**: Los resultados y trazas no deben exponer datos no autorizados, credenciales, mensajes completos ni textos de excepciones.
- **FR-012**: No se afirma cumplimiento PCGE o SUNAT ni se adoptan códigos de cuenta, tratamiento de IGV o reglas contables de otro proyecto. Esos datos, cuando correspondan, los proporciona ADMIN bajo las reglas vigentes del equipo.

### Integración por patrón

| Patrón | Integración futura | Invariantes |
| --- | --- | --- |
| Orquestador | Encauzar solicitudes contables a la capacidad compartida. | Conservar su supervisor y funciones existentes. |
| Jerárquico | Encauzar solicitudes desde su jerarquía a la misma capacidad. | Conservar delegaciones y estado. |
| Descentralizado | Conectar sus handoffs y estado a la misma capacidad. | Conservar los nueve roles existentes, identificadores persistidos, ownership, locks y recuperación, sin nodos duplicados. |

### Key Entities

- **Datos de ingreso manual**: campos de 003 proporcionados por ADMIN, todavía no persistidos.
- **Vista previa temporal**: representación conversacional de esos datos y totales validados; no equivale a un asiento ni a un estado de base de datos.
- **Asiento confirmado**: registro creado por 003 tras confirmación expresa; conserva correlativo, actor, líneas, auditoría e idempotencia.
- **Reversión**: asiento inverso relacionado y motivo, gestionados por 003.

## Success Criteria

- **SC-001**: Todas las solicitudes contables de CUSTOMER, TECHNICIAN o sesiones ausentes se rechazan sin exponer datos ni producir escrituras.
- **SC-002**: Los tres patrones devuelven resultados y controles equivalentes para las mismas operaciones contables, manteniendo distinta su coordinación.
- **SC-003**: Ninguna vista previa, fuente comercial o mensaje sin confirmación crea un asiento.
- **SC-004**: Todos los asientos creados por una confirmación válida cumplen estructura y balance de 003, nacen CONFIRMED y se pueden recuperar sin duplicados tras un reintento.
- **SC-005**: Las reversiones exitosas conservan original, motivo, actor e historial según 003.

## Dependencies and Constraints

- [Spec 001](../001-patrones-multiagente-coherentes/spec.md): equivalencia funcional y diferencias de coordinación.
- [Spec 003](../003-asientos-contables/spec.md), [research D1/D2](../003-asientos-contables/research.md) y [contrato contable](../003-asientos-contables/contracts/accounting.openapi.yaml): autoridad única para operaciones y escritura.
- [Spec 006](../006-registro-compras-proveedores/spec.md): compras, pagos y recepción independientes; FR-015 prohíbe asiento automático.
- Cuentas, importes e IGV no se derivan de datos comerciales. Si el equipo necesita reglas contables específicas futuras, requieren decisión y especificación propias.

## Out of Scope

- Implementar código, migraciones, rutas, tablas, cambios de API o frontend en esta etapa.
- Persistir propuestas, añadir DRAFT o generar asientos automáticos.
- Copiar cuentas, asientos, porcentajes, tasas o reglas de Pollería u otro proyecto.
- Cambiar el comportamiento de 001, 003, 006 o de los patrones existentes.
