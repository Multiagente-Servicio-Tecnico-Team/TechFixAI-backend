# Modelo de datos: Registro de compras a proveedores

Los montos se expresan en PEN y usan `NUMERIC(14,2)`/`Decimal`. Todas las fechas se guardan con zona horaria cuando representan un evento y como `DATE` para fechas del comprobante. IDs son claves generadas por PostgreSQL. Los campos `created_by`/`actor_user_id` se obtienen de la sesión ADMIN.

## Proveedor (`suppliers`, ampliada)

| Campo | Tipo / regla | Notas |
|---|---|---|
| `id` | BIGINT PK | Ya existe |
| `name` | VARCHAR(200), requerido | Conservar campo vigente; razón social visible |
| `tax_id` | VARCHAR(20), opcional, único cuando existe | RUC u otro identificador tributario, sin imponer validación tributaria PLE |
| `contact_name` | VARCHAR(200), nullable | Contacto |
| `contact_email` | VARCHAR(255), nullable | Campo actual |
| `phone` | VARCHAR(30), nullable | Campo actual |
| `address` | TEXT, nullable | Nueva |
| `delivery_lead_days` | INTEGER, nullable, >= 0 | Campo actual |
| `active` | BOOLEAN, default true | Desactivación lógica; historial conserva proveedor |
| `created_at` | TIMESTAMPTZ | Campo actual o agregado si falta |

El nombre, identificador tributario y contacto se copian a la compra al crearla para mantener la evidencia original del comprobante.

## Compra (`supplier_purchases`)

| Campo | Tipo / regla | Notas |
|---|---|---|
| `id` | BIGINT PK | Identificador |
| `supplier_id` | BIGINT FK `suppliers`, RESTRICT | Proveedor original |
| `purchase_order_id` | BIGINT FK `purchase_orders`, nullable, RESTRICT | Enlace opcional, no comparte ciclo de estados |
| `supplier_name_snapshot` | VARCHAR(200), requerido | Nombre a la fecha de registro |
| `supplier_tax_id_snapshot` | VARCHAR(20), nullable | Identificador a la fecha de registro |
| `document_type` | VARCHAR(30), requerido | Tipo interno de comprobante |
| `document_series` | VARCHAR(30), nullable | Serie según comprobante |
| `document_number` | VARCHAR(40), requerido | Número según comprobante |
| `issue_date` | DATE, requerido | Fecha de emisión |
| `due_date` | DATE, nullable | No anterior a issue date cuando se captura |
| `currency` | CHAR(3), default/check `PEN` | Única moneda en esta versión |
| `subtotal`, `tax_total`, `discount_total`, `other_charges`, `total_amount` | NUMERIC(14,2) | No negativos; total derivado/validado contra líneas y ajuste documentado |
| `payment_method` | VARCHAR(20), requerido | `TRANSFER`, `CASH`, `CARD`, `OTHER` |
| `payment_status` | VARCHAR(10), `PENDING`/`PAID` | Independiente del estado de recepción |
| `status` | VARCHAR(24) | `REGISTERED`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CANCELLED` |
| `notes` | TEXT, nullable | Observaciones operativas |
| `created_by` | BIGINT FK `users`, RESTRICT | ADMIN autenticado |
| `created_at`, `updated_at` | TIMESTAMPTZ | Auditoría temporal |

Restricciones: `total_amount >= 0`; no duplicar `(supplier_id, document_type, normalized_series, document_number)` salvo registros cancelados conforme política definida por implementación; la compra cancelada no se elimina físicamente. Las fechas/series originales permanecen inmutables después de guardar; correcciones previas a recepción quedan auditadas.

## Línea (`supplier_purchase_items`)

| Campo | Tipo / regla | Notas |
|---|---|---|
| `id` | BIGINT PK | |
| `purchase_id` | BIGINT FK, CASCADE | Borrado sólo mientras compra no tenga efectos; preferir no borrar compras persistidas |
| `spare_part_id` | BIGINT FK `spare_parts`, nullable, SET NULL | NULL para concepto fuera del catálogo |
| `code_snapshot` | VARCHAR(50), nullable | SKU en el momento de compra |
| `description_snapshot` | VARCHAR(300), requerido | Descripción original |
| `quantity` | NUMERIC(12,3), > 0 | Admite unidades fraccionarias si el negocio lo requiere; inventario entero sólo recibe cantidades enteras |
| `unit_cost` | NUMERIC(14,2), >= 0 | Costo facturado |
| `discount_amount`, `tax_amount`, `line_total` | NUMERIC(14,2), >= 0 salvo que el ajuste se modele explícitamente | `line_total` se valida contra cantidad, costo, descuento e impuesto |
| `created_at` | TIMESTAMPTZ | |

En la primera migración de inventario, sólo se permiten cantidades recibidas enteras para repuestos que incrementan `current_stock` (entero). Conceptos no asociados al inventario pueden conservar cantidad decimal.

## Recepción (`purchase_receipts`) y líneas (`purchase_receipt_items`)

Un evento de recepción es la confirmación de una llegada física. Una compra puede tener varias recepciones parciales hasta recibir sus cantidades facturadas.

| Entidad/campo | Tipo / regla | Notas |
|---|---|---|
| Receipt `id` | BIGINT PK | |
| Receipt `purchase_id` | BIGINT FK, RESTRICT | Compra de origen |
| Receipt `idempotency_key` | UUID, requerido | Único por actor/compra |
| Receipt `received_at` | TIMESTAMPTZ | Momento confirmado |
| Receipt `received_by` | BIGINT FK users, RESTRICT | ADMIN de sesión |
| Receipt `notes` | TEXT, nullable | |
| Receipt item `id` | BIGINT PK | |
| Receipt item `receipt_id` | BIGINT FK, CASCADE | |
| Receipt item `purchase_item_id` | BIGINT FK, RESTRICT | Línea facturada |
| Receipt item `quantity_received` | NUMERIC(12,3), > 0 | Total acumulado nunca excede quantity |
| Receipt item `stock_movement_id` | FK lógico/único cuando aplica | Sólo para producto catalogado con actualización de inventario |

Reintentar la misma clave y payload devuelve la recepción original sin repetir el efecto. Reutilizar clave con payload diferente es conflicto. No se crea movimiento para líneas no enlazadas al catálogo.

## Movimiento de inventario (`inventory_movements`)

| Campo | Tipo / regla | Notas |
|---|---|---|
| `id` | BIGINT PK | |
| `spare_part_id` | BIGINT FK `spare_parts`, nullable, SET NULL | El movimiento conserva snapshots incluso si el catálogo se elimina |
| `code_snapshot`, `name_snapshot` | VARCHAR(50)/VARCHAR(150), requeridos | Evidencia del producto al recibir |
| `purchase_receipt_item_id` | BIGINT FK, UNIQUE | Evita doble movimiento de una línea confirmada |
| `movement_type` | VARCHAR(20), `PURCHASE_RECEIPT` | Movimientos de recepción solamente en este alcance |
| `quantity_delta` | INTEGER, > 0 | Suma a `current_stock` |
| `stock_before`, `stock_after` | INTEGER >= 0 | Evidencia de aplicación |
| `actor_user_id` | BIGINT FK users, RESTRICT | ADMIN confirmado |
| `created_at` | TIMESTAMPTZ | Fecha del evento |

Actualización de movimiento y `spare_parts.current_stock` es atómica. El stock que no se haya recibido no se incrementa.

## Auditoría (`supplier_purchase_audit_events`)

`id`, `purchase_id`, `actor_user_id`, `event_type` (`CREATED`, `UPDATED`, `RECEIPT_CONFIRMED`, `PAYMENT_STATUS_CHANGED`, `CANCELLED`), `changed_fields` JSONB sin secretos, `created_at`. Sólo append; cada mutación relevante inserta el evento en la misma transacción.

## Relaciones y estados

```text
suppliers 1 ── * supplier_purchases * ── 0..1 purchase_orders
supplier_purchases 1 ── * supplier_purchase_items
supplier_purchases 1 ── * purchase_receipts 1 ── * purchase_receipt_items
supplier_purchase_items 1 ── * purchase_receipt_items
purchase_receipt_items 0..1 ── 1 inventory_movements ── 1 spare_parts
```

- Estado de recepción: `REGISTERED → PARTIALLY_RECEIVED → RECEIVED`; `REGISTERED → RECEIVED` cuando una sola recepción completa cantidades. `CANCELLED` sólo si no hubo recepción.
- Estado de pago independiente: `PENDING → PAID`; no hay pagos parciales ni saldo. No se permite devolver `PAID` a `PENDING` sin flujo explícito de corrección auditada.
- Ninguna ruta de compra genera `accounting_entries`.
