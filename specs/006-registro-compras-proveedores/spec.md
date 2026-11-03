# Feature Specification: Registro de compras a proveedores

**Feature Branch**: 006-registro-compras-proveedores  
**Created**: 2026-11-03  
**Status**: Draft  
**Input**: User description: Usar Spec Kit para definir en el backend el registro de compras a proveedores; revisar las tablas existentes y proponer si se reutilizan o crean tablas y qué campos usuales debe tener la sección.

## Clarifications

### Session 2026-11-03

- Q: ¿El comprobante recibido se registra ampliando las órdenes existentes o en un registro separado que pueda vincularse a una orden? → A: Mantener separadas las órdenes y las compras recibidas; una compra puede vincularse opcionalmente a una orden.
- Q: ¿En qué momento debe aumentar el stock al registrar una compra? → A: Solo cuando ADMIN confirma la recepción física; cada recepción se aplica una sola vez y queda trazada.
- Q: ¿Qué seguimiento de pagos quieres para las compras a proveedores? → A: Guardar método y estado pagado/pendiente, sin pagos parciales; el asiento contable permanece independiente.

## User Scenarios & Testing

### User Story 1 - Registrar una compra de proveedor (Priority: P1)

Como ADMIN, quiero registrar un comprobante de compra recibido de un proveedor con sus artículos y costos para conservar el historial de abastecimiento y conocer el costo pagado por cada componente.

**Why this priority**: El registro de compras es el dato central de la funcionalidad y permite rastrear proveedor, comprobante, líneas y total.

**Independent Test**: Ingresar como ADMIN, elegir un proveedor, capturar un comprobante con dos líneas, guardar y volver a consultar el detalle con sus importes.

**Acceptance Scenarios**:

1. **Given** ADMIN seleccionó un proveedor activo y capturó un comprobante válido, **When** guarda la compra, **Then** el registro conserva proveedor, tipo y número de documento, fecha, importes y responsable autenticado.
2. **Given** una compra contiene varios repuestos, **When** ADMIN agrega sus líneas, **Then** cada línea conserva artículo relacionado si existe, descripción de compra, cantidad y costo unitario.
3. **Given** el comprobante ya fue registrado para el mismo proveedor, **When** ADMIN intenta volver a registrarlo, **Then** el sistema señala el posible duplicado y no crea una segunda compra.
4. **Given** el servicio de registro no confirma la operación, **When** falla el guardado, **Then** no se muestra la compra como persistida.
5. **Given** ADMIN registra una compra pagada o pendiente, **When** guarda el comprobante, **Then** el sistema conserva el método y estado de pago indicados, y una compra pendiente no se presenta como pagada.

---

### User Story 2 - Mantener proveedores disponibles para compras (Priority: P2)

Como ADMIN, quiero consultar proveedores activos y registrar uno cuando aún no existe para asociar cada compra con la contraparte correcta.

**Why this priority**: Una compra sin proveedor identificable pierde trazabilidad y no puede relacionarse con sus documentos.

**Independent Test**: Consultar proveedores activos, registrar un proveedor con sus datos comerciales y usarlo en una compra.

**Acceptance Scenarios**:

1. **Given** existen proveedores activos, **When** ADMIN inicia una compra, **Then** puede encontrarlos por nombre o identificador tributario.
2. **Given** el proveedor todavía no está registrado, **When** ADMIN ingresa sus datos requeridos, **Then** puede guardarlo y asociarlo a la compra.
3. **Given** un proveedor tiene compras registradas, **When** deja de operar, **Then** puede desactivarse sin borrar su historial.

---

### User Story 3 - Confirmar recepción de compra (Priority: P2)

Como ADMIN, quiero confirmar cuándo llegaron los artículos para que las existencias reflejen lo recibido y exista una traza del movimiento.

**Why this priority**: Una factura puede registrarse antes de que llegue la mercancía; el inventario debe cambiar cuando los artículos estén físicamente recibidos.

**Independent Test**: Registrar una compra pendiente de recepción, confirmar las cantidades recibidas y verificar que el stock cambia una vez y el movimiento identifica responsable y fecha.

**Acceptance Scenarios**:

1. **Given** una compra registrada aún no recibida, **When** ADMIN consulta inventario, **Then** sus artículos todavía no incrementan el stock.
2. **Given** una compra contiene artículos vinculados al inventario, **When** ADMIN confirma su recepción, **Then** solo las cantidades recibidas incrementan el stock y el sistema registra el responsable y la fecha.
3. **Given** la recepción ya fue confirmada, **When** se repite la misma solicitud, **Then** el stock no vuelve a incrementarse.
4. **Given** un artículo de una línea no está vinculado al catálogo, **When** ADMIN confirma la recepción, **Then** el sistema conserva la línea histórica sin inventar un repuesto.

---

### User Story 4 - Consultar y rastrear compras (Priority: P3)

Como ADMIN, quiero buscar compras y revisar su detalle para verificar documentos, costos, responsables y estado.

**Why this priority**: La consulta y trazabilidad permiten supervisar los egresos y abastecimientos registrados.

**Independent Test**: Buscar compras por proveedor y período, abrir una compra y verificar datos del comprobante, líneas, importes y responsable.

**Acceptance Scenarios**:

1. **Given** hay compras registradas, **When** ADMIN filtra por proveedor, fecha o estado, **Then** la lista solo presenta registros coincidentes.
2. **Given** ADMIN abre una compra, **When** consulta el detalle, **Then** ve los datos originales del proveedor y los valores de cada línea.
3. **Given** una compra cambia de estado o se cancela, **When** ADMIN revisa su historial, **Then** identifica quién efectuó el cambio y cuándo.

### Edge Cases

- El mismo tipo, serie y número de comprobante aparece de nuevo para el mismo proveedor.
- El comprobante tiene varias líneas, descuento, cargo adicional o impuesto; los importes no cuadran con el total informado.
- Un artículo del catálogo fue desactivado o eliminado después de la compra; la línea histórica debe conservar su descripción y costo.
- El proveedor se desactiva después de registrar compras; los registros históricos deben seguir consultables.
- Una cantidad, costo o total es cero, negativo, tiene más de dos decimales o excede la precisión aceptada.
- La compra se guarda y la conexión se interrumpe antes de que la interfaz reciba confirmación.
- Dos ADMIN intentan registrar al mismo tiempo el mismo comprobante.
- Una compra se cancela después de que sus artículos fueron recibidos.
- La compra se registra antes de recibir físicamente los productos.
- La sesión caduca o una cuenta CUSTOMER intenta consultar o modificar compras.
- Repetir o reintentar una confirmación de recepción no debe aplicar dos veces el mismo incremento de stock.

## Requirements

### Functional Requirements

- **FR-001**: Solo ADMIN autenticado puede listar, crear, consultar, actualizar el estado o cancelar compras y administrar proveedores.
- **FR-002**: El sistema debe permitir seleccionar un proveedor activo y conservar la relación histórica con las compras existentes aunque el proveedor se desactive.
- **FR-003**: El sistema debe registrar tipo de comprobante, serie, número, fecha de emisión y vencimiento opcional, moneda, notas y responsable obtenido de la sesión.
- **FR-004**: Cada línea debe conservar repuesto relacionado si existe, código y descripción como fotografía histórica, cantidad, costo unitario, descuento e importe de impuesto aplicable.
- **FR-005**: El registro debe conservar subtotal, impuestos, cargos o descuentos y total; todos los importes deben usar exactitud decimal de dos posiciones.
- **FR-006**: El sistema debe detectar comprobantes duplicados para un mismo proveedor usando tipo, serie y número.
- **FR-007**: ADMIN debe poder listar compras con filtros de proveedor, fecha y estado, y consultar el detalle del encabezado y sus líneas.
- **FR-008**: El sistema debe conservar un historial auditable de creación, recepción, actualización permitida y cancelación, incluyendo responsable y fecha.
- **FR-009**: El sistema debe validar la transición de estado y evitar modificar o borrar físicamente registros que ya tengan efectos en inventario.
- **FR-010**: El sistema debe conservar por separado el ciclo de solicitud al proveedor y el registro del comprobante recibido; una compra puede vincularse opcionalmente con una orden existente.
- **FR-011**: Guardar una compra no debe alterar las existencias; confirmar la recepción física debe sumar cada cantidad recibida una sola vez y registrar el responsable, fecha y artículos afectados.
- **FR-012**: Cada compra debe conservar el método de pago previsto o utilizado y un estado `PAID` o `PENDING`. La primera versión no registra pagos parciales ni calcula saldos.
- **FR-013**: El sistema debe permitir mantener proveedores con nombre legal, identificador tributario, contacto, correo, teléfono, dirección y estado activo.
- **FR-014**: Esta funcionalidad registra compras internas y no genera ni presenta libros electrónicos PLE ni reemplaza la validación tributaria de un contador.
- **FR-015**: La compra no debe crear automáticamente un asiento contable; el registro contable permanece manual e independiente.

### Key Entities

- **Proveedor**: organización que vende bienes o servicios; tiene nombre legal, identificador tributario, datos de contacto y estado.
- **Orden de compra**: solicitud de abastecimiento al proveedor que conserva su ciclo de estado existente.
- **Compra de proveedor**: comprobante recibido del proveedor con identificación, fechas, moneda, importes, estado, responsable y trazabilidad; puede vincularse a una orden.
- **Línea de compra**: artículo o concepto adquirido con cantidad, descripción histórica, costo, descuentos e impuestos.
- **Recepción de compra**: confirmación de que se recibieron bienes; aplica las cantidades recibidas al inventario una sola vez y conserva responsable y fecha.
- **Pago a proveedor**: método y estado pagado o pendiente; no incluye pagos parciales ni saldo en la primera versión.
- **Movimiento de inventario**: variación trazable de stock asociada a una recepción confirmada, con cantidades, responsable y fecha.

## Success Criteria

### Measurable Outcomes

- **SC-001**: ADMIN puede completar y consultar un registro válido de compra en menos de 3 minutos durante una prueba de aceptación.
- **SC-002**: El 100 % de las compras consultadas muestra proveedor, documento, responsable, detalle de líneas y total registrado.
- **SC-003**: El 100 % de los comprobantes duplicados para el mismo proveedor se detecta sin crear una segunda compra.
- **SC-004**: El 100 % de las líneas consultadas conserva costo y descripción históricos aunque el artículo o proveedor cambie de estado.
- **SC-005**: El 100 % de las operaciones no autorizadas de CUSTOMER se rechaza sin exponer información de compras.
- **SC-006**: Los cambios de estado y recepción pueden rastrearse hasta un ADMIN y una fecha.
- **SC-007**: Cada recepción confirmada actualiza el stock una sola vez y permite rastrear el responsable, la fecha y las cantidades aplicadas.
- **SC-008**: El 100 % de las compras muestra su estado pagado o pendiente; ninguna compra pendiente se presenta como pagada.

## Assumptions

- El sistema usa PEN como moneda inicial, manteniendo los importes exactos; cualquier otra moneda requerirá decisión separada.
- La fuente de identidad del responsable es la sesión autenticada ADMIN, nunca un campo libre enviado por el cliente.
- La funcionalidad es un registro operativo interno, no una implementación de cumplimiento tributario ni generación/envío PLE.
- No se contabiliza automáticamente la compra en la sección de asientos contables; las operaciones contables permanecen separadas.
- El esquema de referencia ya contiene suppliers, purchase_orders y purchase_order_items. suppliers tiene nombre, correo, teléfono, plazo estimado y estado; purchase_orders almacena proveedor, total, estado, llegada estimada y fechas; sus líneas almacenan artículo opcional, nombre libre, cantidad, costo y subtotal.
- purchase_orders permanece como registro de órdenes de abastecimiento; las compras recibidas tendrán su propio registro y podrán vincularse a una orden. No existe tabla de movimientos de stock en el esquema de referencia; la recepción debe dejar un historial consultable.
- El acceso administrativo queda restringido a ADMIN, coherente con la administración de contabilidad y tickets.
- En la primera versión, cada compra tiene un único estado de pago (pagado o pendiente) y un método; no se registran abonos ni pagos parciales.

## Dependencies

- Esquema de referencia: contexto/tablas postgres v2.sql.
- Catálogo de repuestos existente y su identificador estable.
- Sesión ADMIN y mecanismo de auditoría del backend.
- Las decisiones de alcance sobre separación de compras y órdenes, recepción física y seguimiento de pagos están resueltas en Clarifications.
