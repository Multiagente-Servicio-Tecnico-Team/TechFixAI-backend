# Modelo conceptual: clientes comerciales y documentos

Este documento complementa el spec 007. Describe el contrato de datos esperado, no una migración ejecutable. El plan fija la estrategia de transición; los nombres/tipos finales de columnas se concretarán en tareas de implementación y la migración se validará contra el esquema vivo.

## Entidades y relaciones

### User (`users`)

- Mantiene identidad de acceso, rol, credenciales y estado de cuenta.
- Un usuario con rol CUSTOMER puede vincularse a cero o un cliente comercial.
- Una cuenta no se crea para representar a un cliente presencial.
- `users.id` continúa identificando al actor que administra la sesión y queda como autoría de eventos.

### Customer (`customers`)

- Perfil comercial de una persona o empresa atendida.
- Campos conceptuales: identificador, nombre visible, teléfono, correo opcional, origen (`MANUAL`/`PORTAL`), estado, cuenta vinculada opcional, actor creador opcional, fechas de creación/actualización.
- `user_id` opcional y único; cuando existe debe apuntar a cuenta elegible CUSTOMER.
- No incluye contraseña, hash, token, rol ni datos de sesión.
- Email y teléfono no son claves únicas globales: puede haber familias, teléfonos compartidos o clientes no registrados. La vinculación de cuentas usa `user_id` y una verificación explícita.
- El perfil conserva contacto comercial actual. El documento histórico guarda snapshots de los valores que deban ser inmutables.
- Restricciones previstas: `user_id` unique nullable FK restrictivo a `users`; `origin` limitado a `MANUAL`/`PORTAL`; nombre/teléfono no vacíos; `created_by_user_id` identifica a quien dio de alta el perfil y no se deriva del cliente.

### Ticket de servicio

- Pertenece a un `customer_id` comercial después de la migración.
- Conserva tipo de servicio, estado, origen y snapshot de contacto relevante a la recepción.
- Puede tener cero o más cotizaciones de servicio.
- La autoría de creación/cambio referencia a `users`, no a `customers`.
- En filas nuevas `customer_id` es obligatorio. En transición se agrega relación nueva y se hace backfill antes de imponer `NOT NULL`; los snapshots legados se conservan aun después de retirar `tickets.customer_id -> users.id`.

### Cotización

- Pertenece a un cliente comercial.
- `ticket_id` es opcional en el modelo general: requerido para cotización de servicio y nulo para cotización de venta directa.
- Conserva tipo, estado de oferta, fechas, observaciones, actor, snapshot de cliente y total calculado; las líneas conservan artículo/código/nombre/precio/cantidad/subtotal de la oferta.
- Las líneas asociadas al inventario validan el artículo actual al crear la cotización; la copia histórica no cambia si el catálogo cambia después.
- Una cotización de venta aceptada reserva sus cantidades de forma atómica hasta que se confirme el pago o la oferta se rechace, cancele o venza. El vencimiento debe estar definido; al vencer sin pago, la reserva se libera. Al confirmar el pago, la reserva se convierte en movimiento de salida asociado a la venta.
- Restricción conceptual: quote de servicio implica `ticket_id NOT NULL` y `ticket.customer_id = quote.customer_id`; `DIRECT_SALE` implica `ticket_id NULL`. La transición no permite combinaciones parciales.
- Oferta guarda actor creador/aceptante, timestamps, origen, vencimiento y snapshots de contacto/precio/línea.

### Pago

- Pertenece a un cliente comercial y referencia la cotización que origina el cobro.
- Puede mantener `ticket_id` nullable durante la transición o derivar el ticket mediante la cotización de servicio; el modelo final debe evitar exigir ticket en venta directa.
- Estado de pago (PENDING/COMPLETED/REFUNDED) independiente del estado de oferta.
- Un pago completado conserva método, referencia disponible, confirmador y fecha verificable.
- Ticket es nullable o derivado de la cotización solo para el caso de servicio; el vínculo base es cliente y cotización, con consistencia de `customer_id` en todos los documentos.
- Restricciones previstas: actor/fecha obligatorios al pasar a `COMPLETED`; confirmación repetida idempotente; como máximo un pedido por quote/pago exitoso.

### Venta/Pedido

- Se crea tras confirmación verificable del pago de una cotización de venta.
- Pertenece al cliente comercial y conserva referencia única a cotización pagada y pago confirmado.
- Conserva líneas, cantidades, precios y snapshots del momento de venta; nunca se reconstruye desde el catálogo cambiante.
- Estados de preparación/entrega no sustituyen el estado financiero del pago.
- Referencias únicas a `quote_id` y `payment_id`, mismo customer en quote/payment/order; preservar detalle como snapshot y no borrar en cascada datos financieros.

### Reserva de inventario

- Una reserva por cotización directa de venta; estado `RESERVED`, `RELEASED` o `CONSUMED`, `expires_at` obligatorio mientras esté reservada y timestamps/actor para aceptar/liberar/consumir.
- Cada línea referencia quote detail y repuesto (con snapshots de código/nombre), cantidad positiva y estado heredado de cabecera. Índice único evita duplicar la reserva de la misma línea de quote.
- Disponible para aceptación = `spare_parts.current_stock` menos cantidades de reservas activas no vencidas. No se almacena un segundo saldo autoritativo editable.
- La operación bloquea IDs de artículo en orden estable y cambia conjuntamente reserva + estado de oferta. Si una línea falla por stock, rollback completo sin aceptación ni reserva parcial.
- Las ediciones administrativas bloquean el artículo y rechazan un nuevo stock menor que las reservas activas. Borrar/desactivar un artículo reservado se rechaza.
- Extender `inventory_movements` con `sales_order_item_id` nullable; hacer nullable la FK `purchase_receipt_item_id` existente; añadir un check XOR para exigir exactamente un origen entre recepción y línea de pedido, junto con un check que empareje origen y `movement_type` (`PURCHASE_RECEIPT`/`SALE`). Mantener referencias únicas por línea de origen, `ON DELETE RESTRICT`, actor y snapshots. La migración debe conservar sin cambios los movimientos de compra existentes.

## Estados e invariantes del flujo de venta

| Agregado | Estados mínimos | Transición e invariantes |
|---|---|---|
| Cotización de venta | `PENDING → ACCEPTED → CANCELLED/EXPIRED`; rechazo desde pendiente | Aceptación explícita antes del vencimiento y con reserva completa; la oferta no significa pago. |
| Reserva | `RESERVED → RELEASED` o `RESERVED → CONSUMED` | Liberación idempotente por rechazo/cancelación/expiración sin cobro; consumo atómico con pago y salida de stock. |
| Pago | `PENDING → COMPLETED/FAILED`; reembolsos conservan su ciclo separado | `COMPLETED` requiere confirmación ADMIN auditable; repetición idempotente. |
| Pedido/venta | `PAID → PREPARING → FULFILLED`; cancelación compensatoria | Un pedido por quote/pago. El estado comercial no sustituye al estado financiero. |

La expiración se valida al leer/aceptar y se libera idempotentemente mediante mantenimiento operativo cuando esté disponible; no se dependerá exclusivamente de un scheduler para impedir la aceptación de una oferta vencida.

## Migración conceptual

0. Reconciliar el esquema de destino contra migraciones realmente aplicadas e inventariar constraints/FKs vivas. Introducir ledger sin marcar migraciones previas como aplicadas sin verificación.
1. Crear perfiles `customers` vinculados por `user_id` para los usuarios referenciados como clientes en tickets, pagos, cotizaciones u otras relaciones de clientes.
2. Crear un perfil manual individual por cada ticket legado sin usuario y con datos de contacto. No consolidar tickets históricos basándose solo en correo o teléfono.
3. Ejecutar una limpieza de datos de prueba como paso explícito, auditado y acotado: borrar únicamente los ocho tickets `SALE` identificados por el propietario en la base local revisada el 2026-11-03 y solo sus cotizaciones, pagos, eventos y otras filas dependientes confirmadas como parte de esa prueba. Primero verificar IDs/conjunto esperado, estados y conteos de dependencias; abortar sin mutación si difieren. Registrar conteos previos/posteriores. No usar una condición general por tipo `SALE` ni aplicar la limpieza a otros entornos. No inferir que un pago está completado.
4. Añadir relaciones nuevas de ticket/pago/cotización a `customers` y poblarlas sin borrar las relaciones antiguas durante la transición.
5. Heredar el perfil de cotizaciones legadas desde el cliente de su ticket. Poblar pago desde su `customer_id`/ticket previo y validar que ambas fuentes coincidan; reportar inconsistencias, no elegir silenciosamente.
6. Para los registros que se conservan, preservar IDs, importes, estados, líneas, fechas, códigos, referencias y auditoría. Excluir del requisito de retención solo las filas dependientes verificadas de los ocho tickets de prueba cuya eliminación fue aprobada. No reinterpretar adelantos de ticket como pagos ni cambiar estados por inferencia.
7. Verificar conteos por tabla, relaciones huérfanas, suma de pagos y propietario resuelto antes/después. No retirar columnas/constraints antiguas hasta que la compatibilidad esté verificada.
8. La reversión debe poder volver al esquema previo mientras se conserven las columnas anteriores. La eliminación autorizada de las filas de prueba debe ser un paso separado de la migración estructural, con respaldo y reporte propio; la reversión de esquema no reconstruye automáticamente los datos borrados.

## Transición y verificación

1. **Expand**: columnas/FKs nuevas nullable, tablas nuevas, índices no destructivos y compatibilidad de lectura/escritura definida.
2. **Backfill**: crear customer por usuario sin fusionar por correo/teléfono; manual legado individual por ticket/contacto. Guardar mapeo origen→customer para auditar y reanudar.
3. **Validate**: comparar conteos/IDs, nulabilidad, relaciones, total de quote vs líneas y pagos sin owner; abortar si hay inconsistencias no resueltas.
4. **Switch**: actualizar servicios/repositorios/rutas a `customer_id`; conservar lecturas anteriores durante ventana de compatibilidad hasta sincronizar consumidores.
5. **Constrain/contract**: imponer checks/NOT NULL/índices y retirar FK/columnas de user-as-customer solo tras validar datos y consumidores.
6. **Cleanup aprobado**: operación independiente con manifiesto de IDs exactos de los ocho tickets SALE de prueba del destino autorizado, preflight de todos los hijos, conteos y backup. Verificar el manifiesto, no solo que existan ocho tickets del mismo tipo.

## Borrado y retención

- Las cuentas y clientes relacionados a documentos históricos se desactivan; no se borran en cascada.
- Tickets, cotizaciones pagadas, pagos, ventas y eventos de auditoría se cancelan/anulan mediante estados y operaciones compensatorias auditables.
- Los clientes manuales duplicados se conservan separados hasta que una acción administrativa verificada los vincule o fusione con una bitácora de reasignación.

## Riesgos de compatibilidad conocidos

- Hoy `tickets.customer_id`, `payments.customer_id` y varios flujos de chat/portal representan el ID de `users`, mientras rutas de administración buscan clientes por correo consultando esa misma tabla.
- `quotes.ticket_id` es NOT NULL y pagos requieren `ticket_id`; las cotizaciones de venta sin ticket exigen modificar esos contratos y revisar reembolsos/logística que hoy llegan al ticket.
- El cambio impacta filtrado de tickets propios, aceptación/rechazo de cotización, pagos, reembolsos, garantías, logística, herramientas de los tres patrones y pruebas de contrato. Mantener la identidad de sesión como user ID y resolver el customer profile en el límite de aplicación.
- La base vigente no expone una tabla de historial de migraciones. La planificación debe indicar cómo comprobar si cada migración se aplicó y no asumir que una carpeta de archivos equivale a un ledger.

## Componentes backend revisados

- `app/accounts/models.py` y `app/accounts/session.py`: `SessionCustomer.id` es el ID de usuario autenticado; conservar esta identidad y resolver el perfil comercial en la capa de aplicación.
- `app/adapters/api/admin_tickets.py` y `app/adapters/persistence/admin_tickets.py`: alta/consulta administrativa usa contacto manual y una búsqueda de clientes por correo contra `users`; separar esa búsqueda y sus respuestas para `customers`.
- `app/adapters/api/chat.py`, `app/adapters/persistence/tickets.py` y `app/application/tickets.py`: el portal pasa el ID de sesión a consultas de tickets; resolver el perfil asociado y filtrar por él.
- `app/application/quotes.py` y `app/database/repository.py`: aceptación de cotización exige `ticket_id`, comprueba ownership por `tickets.customer_id` y crea pago con ticket/quote/user. El flujo directo SALE del Jerárquico hoy crea ticket antes de la oferta.
- `app/database/repository.py`: operaciones de reembolsos, garantías y logística consultan el propietario a través de `users`/`tickets`; el plan debe cubrir sus dependencias si pagos o ventas quedan sin ticket.
- Pruebas revisadas: `tests/unit/test_ticket_management.py`, `tests/integration/test_admin_ticket_api.py`, `tests/contract/test_admin_ticket_list_contract.py`, `tests/contract/test_admin_ticket_create_contract.py`, `tests/contract/patterns/test_quote_contract.py`, `tests/unit/infrastructure/test_expanded_schema_contract.py` y `tests/integration/test_hierarchical_workflows.py`.
- Migraciones existentes: `sql/migrations/003_accounting_entries.sql`, `004_admin_ticket_management.sql` y `005_supplier_purchases.sql`. La estructura actual no registra una tabla de versión aplicada; el plan debe definir cómo evitar repetir una migración sin ledger.
