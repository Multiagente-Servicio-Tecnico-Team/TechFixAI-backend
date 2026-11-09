# Feature Specification: Gestión de órdenes de compra a proveedores

**Feature Branch**: `010-ordenes-compra-proveedores`  
**Created**: 2026-11-09  
**Status**: Draft  
**Input**: User request to add backend API for supplier purchase orders, using existing `purchase_orders` and `purchase_order_items`, while keeping stock unchanged until physical receipt.

## User Scenarios & Testing

### User Story 1 - Crear y consultar órdenes de compra (Priority: P1)

Como ADMIN, quiero crear una orden para un proveedor con artículos del inventario o conceptos libres, cantidades y costos, para formalizar el abastecimiento y consultar lo solicitado.

**Independent Test**: Crear una orden en borrador con dos líneas, recuperarla por ID y comprobar proveedor, líneas, totales y estado.

**Acceptance Scenarios**:

1. **Given** un ADMIN autenticado y un proveedor activo, **When** registra una orden con una o más líneas válidas, **Then** el backend persiste encabezado y líneas en una transacción y devuelve el detalle completo.
2. **Given** una línea ligada a un repuesto, **When** se guarda la orden, **Then** se conserva el ID numérico del repuesto y una descripción y costo unitario históricos.
3. **Given** una línea de concepto libre, **When** se guarda la orden, **Then** se conserva su descripción sin crear un repuesto ni afectar existencias.
4. **Given** la orden está en borrador, **When** ADMIN cambia proveedor, fecha estimada o líneas, **Then** los cambios se validan, recalculan y auditan.
5. **Given** la solicitud no se guarda, **When** ocurre un error de persistencia o validación, **Then** no queda un encabezado sin líneas ni se informa éxito.

### User Story 2 - Emitir y cancelar órdenes (Priority: P1)

Como ADMIN, quiero emitir una orden al proveedor y cancelar una orden que ya no se ejecutará, conservando responsable, fecha y motivo.

**Independent Test**: Emitir una orden en borrador, consultar su autor y marca de tiempo, y luego cancelar otra orden sin recepción.

**Acceptance Scenarios**:

1. **Given** una orden válida en borrador, **When** ADMIN la emite, **Then** cambia a `ISSUED` y se registra quién y cuándo la emitió.
2. **Given** una orden emitida o parcialmente recibida, **When** ADMIN cancela las cantidades pendientes, **Then** la orden queda `CANCELLED`, las recepciones ya realizadas permanecen y no se revierte su stock.
3. **Given** una orden ya recibida o cancelada, **When** se intenta una transición incompatible, **Then** el backend responde conflicto y conserva el estado.
4. **Given** un usuario sin rol ADMIN, **When** intenta emitir, cancelar o editar una orden, **Then** el backend rechaza la operación sin revelar datos protegidos.

### User Story 3 - Registrar recepción física contra la orden (Priority: P1)

Como ADMIN, quiero registrar recepciones parciales o completas directamente contra las líneas de la orden, antes o después de recibir la factura, para que el inventario refleje únicamente los artículos que llegaron físicamente.

**Independent Test**: Emitir una orden de 10 unidades, recibir 4, verificar que el stock aumenta en 4 y que la orden indica 4 recibidas y 6 pendientes; repetir la misma solicitud y confirmar que no hay un segundo incremento.

**Acceptance Scenarios**:

1. **Given** una orden emitida, **When** ADMIN registra una recepción parcial con cantidades por línea, **Then** la recepción y los movimientos de inventario se guardan atómicamente y el stock aumenta exactamente por las cantidades recibidas.
2. **Given** una línea ya recibió parte de su cantidad, **When** llega otra entrega, **Then** se acepta solo si el acumulado no excede la cantidad ordenada y se actualiza el pendiente.
3. **Given** la recepción se confirma antes de crear la factura, **When** se registra la recepción, **Then** queda asociada a la orden y no requiere un comprobante de compra previo.
4. **Given** una línea es un concepto libre sin `spare_part_id`, **When** se recibe, **Then** queda trazada la cantidad y descripción pero no se modifica inventario.
5. **Given** se reintenta una recepción con la misma clave de idempotencia y contenido, **When** el backend la procesa, **Then** devuelve la recepción anterior y no duplica movimientos.
6. **Given** una línea no corresponde a la orden, la cantidad excede lo pendiente, o la orden no está emitida, **When** se intenta recibir, **Then** el backend rechaza toda la operación sin aplicar stock parcialmente.

### User Story 4 - Vincular la factura recibida a la orden (Priority: P2)

Como ADMIN, quiero asociar una compra/comprobante del proveedor a la orden correspondiente, aunque la recepción física ya se haya registrado, para consultar conjuntamente lo pedido, lo recibido y lo facturado.

**Independent Test**: Registrar recepción desde la orden, crear luego una compra de proveedor vinculada a esa misma orden y comprobar que consultar cualquiera de los recursos conserva el vínculo y no vuelve a aumentar stock.

**Acceptance Scenarios**:

1. **Given** existe una orden, **When** ADMIN crea una compra de proveedor con su `purchase_order_id`, **Then** el proveedor de la compra debe coincidir con el de la orden y ambos detalles muestran su relación.
2. **Given** una factura corresponde a una orden ya recibida, **When** se registra o consulta la factura, **Then** no se genera una segunda recepción ni un incremento duplicado de stock.
3. **Given** se emiten varias facturas parciales para una orden, **When** se vinculan, **Then** cada comprobante conserva sus propios importes, estados de pago y fechas sin sobrescribir los datos de la orden.
4. **Given** una factura o línea se vincula a una orden distinta o a otro proveedor, **When** se intenta guardar, **Then** el backend rechaza la relación con un error de validación o conflicto.

### User Story 5 - Buscar órdenes e inspeccionar su historial (Priority: P2)

Como ADMIN, quiero listar órdenes con filtros y consultar su historial para dar seguimiento al abastecimiento.

**Independent Test**: Listar órdenes por proveedor, estado y fecha; abrir una orden y verificar líneas, recepciones, facturas vinculadas y eventos de auditoría.

**Acceptance Scenarios**:

1. **Given** hay órdenes, **When** ADMIN filtra por proveedor, estado o rango de fechas y pagina resultados, **Then** recibe solo coincidencias y metadatos de paginación.
2. **Given** ADMIN consulta una orden, **When** se devuelve el detalle, **Then** aparecen cantidades ordenadas, recibidas y pendientes, importes, historial y facturas vinculadas.

## Edge Cases

- Proveedor inactivo al crear una orden; las órdenes históricas siguen visibles si luego el proveedor se desactiva.
- Lista vacía, líneas repetidas para el mismo repuesto, cantidades o costos nulos, negativos o fuera de precisión.
- Un repuesto se desactiva o elimina después de ordenar; la línea conserva su snapshot histórico y una recepción no debe inventar ni recrear ese repuesto.
- Recepción parcial seguida de cancelación: se preserva lo recibido y se cancela solo lo pendiente, sin reversar movimientos ya aplicados.
- Reintentos de creación, emisión, cancelación o recepción después de un timeout; las operaciones con efecto no deben duplicarse.
- Dos ADMIN reciben simultáneamente la misma línea; el acumulado recibido debe validarse bajo concurrencia.
- Factura registrada antes de la recepción, recepción antes de factura, múltiples recepciones y múltiples comprobantes para una misma orden.
- Factura con proveedor diferente, línea que no pertenece a la orden, importe diferente del costo ordenado o cantidad facturada diferente de la recibida.
- La orden se elimina o actualiza mientras existen recepciones, facturas o movimientos relacionados; se debe conservar integridad e historial.
- Sesión caducada o rol CUSTOMER intentando consultar, crear o modificar órdenes.

## Requirements

### Functional Requirements

- **FR-001**: Solo una cuenta autenticada con rol `ADMIN` puede listar, crear, consultar, editar, emitir, cancelar o recibir órdenes de compra.
- **FR-002**: El backend debe exponer contratos API para crear, listar con filtros/paginación, consultar detalle, editar órdenes en borrador, emitir, cancelar y registrar/listar recepciones de orden.
- **FR-003**: Crear una orden requiere proveedor activo y al menos una línea válida. Los totales se calculan en backend usando precisión decimal; el cliente no es autoridad para importes calculados.
- **FR-004**: Las líneas de catálogo guardan `spare_part_id` numérico, cantidad, costo unitario y snapshot de código/descripción; las líneas libres guardan descripción sin referenciar inventario.
- **FR-005**: El estado inicial será `DRAFT`. Las transiciones permitidas son `DRAFT -> ISSUED -> PARTIALLY_RECEIVED -> RECEIVED`; desde `ISSUED` o `PARTIALLY_RECEIVED` se permite `CANCELLED`, conservando cantidades recibidas. `DRAFT -> CANCELLED` también está permitido. No se permiten otras transiciones.
- **FR-006**: Solo `DRAFT` permite editar proveedor, fecha estimada y líneas. Emitir y cancelar requieren acción explícita de ADMIN; la emisión registra actor y fecha. La cancelación exige motivo y registra actor y fecha. Las líneas emitidas no se reescriben; cambios posteriores requieren cancelar lo pendiente y crear otra orden.
- **FR-007**: El encabezado debe mostrar importes calculados de sus líneas y moneda PEN, con importes almacenados en tipo decimal exacto. No se aceptan totales suministrados por el cliente como fuente de verdad.
- **FR-008**: Registrar una orden, editarla o emitirla nunca reserva ni modifica stock. No se crea movimiento de inventario por la mera existencia de una orden.
- **FR-009**: La recepción debe identificar cantidades por línea de orden, fecha y ADMIN responsable obtenido de la sesión. Cada recepción se persiste con sus movimientos de inventario en la misma transacción.
- **FR-010**: Solo se reciben cantidades positivas de líneas pertenecientes a la orden; la cantidad acumulada no puede exceder lo ordenado. Una cancelación posterior a una recepción conserva lo recibido y cancela únicamente el saldo pendiente.
- **FR-011**: Las líneas libres se pueden recibir y auditar, pero no alteran stock. Una línea vinculada a repuesto produce un movimiento `PURCHASE_RECEIPT` por la cantidad efectivamente recibida.
- **FR-012**: La recepción soporta `Idempotency-Key`; reintentar la misma clave y payload devuelve el resultado previo y no duplica recepción ni movimientos; reutilizar la clave con otro payload produce conflicto.
- **FR-013**: La compra/comprobante de proveedor continúa siendo una entidad independiente. Puede tener vínculo opcional a una orden existente, solo si corresponde al mismo proveedor. Vincular o registrar el comprobante no vuelve a aplicar al stock cantidades recibidas previamente desde la orden.
- **FR-014**: El backend debe conservar trazabilidad entre orden, líneas, recepciones, movimientos de inventario y comprobantes vinculados, sin sustituir los datos históricos de unos por los de otros.
- **FR-015**: Las operaciones y transiciones conservan auditoría con actor autenticado, marca de tiempo y, para cancelación, motivo. No se permite borrado físico de órdenes con recepciones, movimientos o compras vinculadas.
- **FR-016**: Las rutas nuevas deben responder errores coherentes: `401` sesión ausente/vencida, `403` rol insuficiente, `404` no encontrado, `409` estado incompatible/duplicidad/concurrencia, `422` campos inválidos y `503` persistencia no disponible sin efectos parciales.
- **FR-017**: La implementación de esquema debe ser una migración versionada, aditiva y segura para datos existentes. Debe ampliar el modelo de órdenes/recepciones/auditoría para admitir recepción directa contra orden y conciliación posterior con comprobantes, sin borrar ni reinterpretar datos existentes.
- **FR-018**: La consulta de orden debe reportar, por línea, cantidad ordenada, recibida, pendiente y, cuando exista, facturada; debe distinguir estos valores sin inferir que el importe facturado fue pagado.
- **FR-019**: Esta API es interna y operativa; no genera ni presenta PLE, no registra pagos parciales y no crea asientos contables automáticamente.

### API Contract Scope

Las rutas previstas se definen en `contracts/purchase-orders.openapi.yaml`. Todas requieren la cookie de sesión vigente y rol ADMIN:

- `GET /api/admin/purchase-orders`
- `POST /api/admin/purchase-orders`
- `GET /api/admin/purchase-orders/{order_id}`
- `PATCH /api/admin/purchase-orders/{order_id}` (solo `DRAFT`)
- `POST /api/admin/purchase-orders/{order_id}/issue`
- `POST /api/admin/purchase-orders/{order_id}/cancel`
- `POST /api/admin/purchase-orders/{order_id}/receipts`
- `GET /api/admin/purchase-orders/{order_id}/receipts`

La ruta existente `POST /api/admin/purchases` conserva la compra recibida separada y su `purchase_order_id` opcional. Su contrato debe ampliarse solo si hace falta asociar líneas de factura con líneas de orden para conciliar cantidades; no se debe crear un segundo movimiento de inventario por esa asociación.

### Key Entities

- **PurchaseOrder**: solicitud a proveedor con identificador público, proveedor, estado, moneda, fecha estimada, totales, actor/fechas de auditoría y líneas.
- **PurchaseOrderItem**: línea de repuesto o concepto libre con cantidad ordenada, costo, subtotal y snapshots.
- **PurchaseOrderReceipt**: recepción física contra una orden, con fecha, ADMIN, idempotencia, notas y líneas recibidas.
- **PurchaseOrderReceiptItem**: cantidad recibida de una línea de orden; puede referir el movimiento de inventario generado si es un repuesto.
- **SupplierPurchase**: comprobante recibido existente, separado de la orden; puede vincularse a una orden y conservar sus propios importes/estado de pago.
- **InventoryMovement**: movimiento por recepción confirmada; nunca se genera al crear o emitir la orden.
- **PurchaseOrderAuditEvent**: actor, evento, fecha y datos de transición relevantes.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100 % de órdenes y transiciones ejecutadas por rol distinto de ADMIN se rechazan.
- **SC-002**: Crear, editar y emitir una orden produce cero cambios de stock y cero movimientos de inventario.
- **SC-003**: Para cada recepción válida, el delta de stock coincide exactamente con la suma de cantidades recibidas de repuestos; las líneas libres producen delta cero.
- **SC-004**: Una misma clave de idempotencia no produce más de una recepción ni un movimiento por artículo.
- **SC-005**: Ninguna cantidad recibida acumulada supera la cantidad ordenada, incluso bajo solicitudes concurrentes.
- **SC-006**: El detalle permite distinguir cantidades ordenadas, recibidas, pendientes y facturadas para el 100 % de líneas.
- **SC-007**: Vincular una factura a una orden ya recibida no genera un segundo incremento de stock.
- **SC-008**: Todas las emisiones, recepciones y cancelaciones muestran el actor y fecha; todas las cancelaciones conservan su motivo.
- **SC-009**: Errores durante la recepción no dejan cambios parciales en existencias, recepciones ni movimientos.

## Assumptions

- El usuario eligió que ADMIN gestione borradores, emisión y cancelación; no existe un flujo de aprobación por otra persona.
- El usuario eligió registrar la recepción contra la orden antes o después de la factura.
- Una orden no crea reserva ni compromiso de stock; el único efecto en inventario ocurre en la recepción física confirmada.
- Se conservan las tablas actuales `purchase_orders`, `purchase_order_items`, `supplier_purchases`, `supplier_purchase_items`, `purchase_receipts`, `purchase_receipt_items` e `inventory_movements` cuando sean compatibles; cualquier cambio se define en el plan como migración versionada.
- Las recepciones directas de una orden se modelan de manera que sus movimientos puedan conciliarse al asociar después una factura. Una asociación de comprobante por sí sola no altera inventario.
- PEN es la moneda inicial, coherente con el módulo de compras existente.
- Los IDs de repuestos son identificadores numéricos internos; el SKU no sustituye el FK.

## Dependencies

- Sesión autenticada y autorización ADMIN existente.
- API, repositorio y modelos actuales de proveedores, compras a proveedores, recepciones e inventario.
- Tablas de órdenes `purchase_orders` y `purchase_order_items` existentes, y migraciones versionadas del backend.
- Catálogo `spare_parts` y trazabilidad de `inventory_movements`.
