# Research: Registro de compras a proveedores

## Decisiones

### Mantener separadas orden y compra recibida

- **Decisión**: conservar `purchase_orders` y `purchase_order_items` como solicitud al proveedor. Agregar `supplier_purchases` y sus líneas; la relación a una orden es opcional.
- **Rationale**: una orden expresa lo solicitado; el comprobante recibido documenta lo facturado/entregado. Pueden diferir en fecha, cantidad y total.
- **Alternativas consideradas**: reutilizar `purchase_orders` para ambos ciclos. Descartada porque mezcla estados y sobrescribe la diferencia entre solicitado, facturado y recibido.
- **Evidencia local**: `contexto/tablas postgres v2.sql` define órdenes con proveedor, total, estado y llegada estimada, pero no registra número de factura, método/estado de pago ni responsable de la compra.

### Registrar recepciones y stock en transacción

- **Decisión**: una compra admite recepciones con cantidades parciales en eventos separados. Cada evento es idempotente y, en una transacción, crea auditoría/movimientos y suma sólo la cantidad recibida de líneas vinculadas a `spare_parts`. La compra queda `PARTIALLY_RECEIVED` o `RECEIVED` según lo recibido acumulado.
- **Rationale**: permite representar entregas parciales sin declarar disponible lo que aún no llegó; reintentos no deben duplicar existencias. Coincide con la decisión explícita del usuario de actualizar stock al confirmar recepción.
- **Alternativas consideradas**: aumentar stock al guardar la factura, descartada porque factura no prueba recepción física; confirmar una sola vez la compra completa, descartada porque no permite representar recepciones en fechas distintas.
- **Evidencia local**: `spare_parts.current_stock` es el stock actual; no existe libro de movimientos de stock en el esquema de referencia. `InventoryRepositoryAdapter` usa `session.begin()` para cada operación de escritura.

### Idempotencia y concurrencia

- **Decisión**: cada comando de recepción lleva `Idempotency-Key` UUID, único por actor/compra; la base de datos garantiza unicidad. La fila de compra se bloquea durante el cálculo y aplicación de cantidades. Recepción y movimientos se guardan atómicamente.
- **Rationale**: el cliente puede reintentar tras perder una respuesta HTTP; la clave impide duplicar operaciones y el bloqueo evita competir por saldos/cantidades recibidas.
- **Alternativas consideradas**: deduplicar sólo en memoria o confiar en la interfaz, descartadas porque no sobreviven a reinicios ni a peticiones concurrentes.
- **Evidencia local**: `app/adapters/api/accounting.py` acepta `Idempotency-Key`; migración `sql/migrations/003_accounting_entries.sql` conserva clave y hash con índice único parcial.

### Snapshots e historial no destructivo

- **Decisión**: conservar nombre/código de proveedor y nombre/código de producto en la compra/línea/movimiento; relaciones opcionales a catálogo/orden no eliminan el snapshot. Estados terminales no se borran; cambios quedan en eventos de auditoría.
- **Rationale**: `spare_parts` y `suppliers` pueden cambiar o desactivarse posteriormente, pero el comprobante histórico debe seguir legible.
- **Alternativas consideradas**: depender sólo de joins al catálogo actual, descartada porque cambia el pasado o pierde texto cuando se elimina un elemento.
- **Evidencia local**: `purchase_order_items.spare_part_id` ya es nullable con `ON DELETE SET NULL`, mientras el nombre libre permite conservar la descripción.

### Límites de pagos y contabilidad

- **Decisión**: guardar método y estado `PAID`/`PENDING` en la compra; sin cuotas, abonos, saldo ni conciliación. No crear asiento automáticamente.
- **Rationale**: respeta la decisión del usuario y el registro contable ya es un flujo administrativo independiente.
- **Alternativas consideradas**: tabla de transacciones de pago o asiento derivado, fuera del alcance confirmado.
- **Evidencia local**: spec 003 asientos contables y constitución del backend separan pagos pendientes de operaciones completadas y exigen registro manual independiente.

### Migración aditiva y esquema actual

- **Decisión**: crear `sql/migrations/005_supplier_purchases.sql` transaccional e idempotente, sin eliminar ni recrear tablas. Ampliar `suppliers` con campos que faltan (razón social, identificador fiscal, dirección; conservar los actuales) y agregar compras, líneas, recepciones, movimientos y eventos.
- **Rationale**: el SQL de referencia es un esquema de instalación con `DROP TABLE` y no debe usarse para actualizar una base existente. El proyecto usa migraciones versionadas para cambios conservadores.
- **Alternativas consideradas**: editar/re-ejecutar `contexto/tablas postgres v2.sql`, descartada por su carácter destructivo.
- **Evidencia local**: `sql/migrations/003_accounting_entries.sql` y `004_admin_ticket_management.sql` usan `BEGIN`/`COMMIT` y cambios aditivos.

## Convenciones de implementación observadas

- API FastAPI en `app/adapters/api`; composición de router en `app/infrastructure/chat_app.py`.
- Autorización por dependencia `require_admin`; no aceptar actor/responsable en payload.
- Persistencia de escrituras dentro de `session.begin()` y SQLAlchemy Core `text()`.
- Validación HTTP con Pydantic `extra="forbid"`; errores estructurados sin detalles SQL.
- Importes contables como `Decimal` y columnas PostgreSQL `NUMERIC`.
- La estructura de tests incluye pruebas unitarias de adapters/repository e integración API; fijar fixtures aislados y nunca apuntar pruebas de mutación a la base `.env`.

## Incógnitas resueltas

No quedan decisiones de alcance abiertas del spec. La recepción parcial se adopta como detalle de diseño para cumplir la frase “sólo las cantidades recibidas” y permitir más de una llegada física; no cambia que cada recepción se confirma explícitamente y una sola vez.
