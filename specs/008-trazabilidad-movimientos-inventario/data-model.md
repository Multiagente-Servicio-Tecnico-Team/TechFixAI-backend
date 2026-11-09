# Modelo de datos: Trazabilidad de movimientos de inventario

## Entidad existente `spare_parts`

| Campo | Cambio | Regla |
|---|---|---|
| `id`, `code`, `name` | Sin cambio | Identidad del artículo; código/nombre se copian como snapshots. |
| `current_stock` | Sin cambio de tipo | Entero >= 0. Solo cambia junto a un movimiento. |
| `active` | Sin cambio de tipo | Retiro del catálogo conserva la fila y sus movimientos. |
| `minimum_threshold` | Sin cambio | No altera cantidades de movimientos. |

## Entidad ampliada `inventory_movements`

| Campo | Estado | Regla |
|---|---|---|
| `id`, `spare_part_id`, `purchase_receipt_item_id`, `sales_order_item_id` | Existentes | Mantener identidad y FKs. Una fila identifica exactamente un origen. |
| `movement_type` | Ampliar | `OPENING_BALANCE`, `ADJUSTMENT_IN`, `ADJUSTMENT_OUT`, `PURCHASE_RECEIPT`, `SALE`. |
| `code_snapshot`, `name_snapshot` | Existentes | Inmutables; representan datos al momento del movimiento. |
| `quantity_delta` | Existente | Entrada > 0, salida < 0; corte >= 0 con stock_before=0. |
| `stock_before`, `stock_after` | Existentes | >= 0 y `stock_after = stock_before + quantity_delta`. |
| `actor_user_id` | Relajar solo para sistema | Requerido cuando actor es USER; nulo únicamente para corte SYSTEM. |
| `actor_kind` | Nuevo | `USER` o `SYSTEM`; SYSTEM solo para migración de corte. No crear cuenta falsa. |
| `reason` | Nuevo | Obligatorio en apertura/ajuste; corte lleva motivo automático. Recepción/venta puede usar origen como detalle. |
| `idempotency_key`, `request_hash` | Nuevos | Obligatorios en apertura/ajuste; hash canónico. Legacy puede ser nulo; compra/venta idempotente por origen. |
| `created_at` | Existente | Fecha de aplicación, no se edita. |

## Tipos y relaciones

| Tipo | Signo | Origen | Autoría |
|---|---:|---|---|
| `OPENING_BALANCE` manual | >= 0 | Sin línea compra/venta | USER autenticado, motivo requerido; stock_before=0. |
| `OPENING_BALANCE` corte | >= 0, incluso cero | Sin línea compra/venta | SYSTEM; motivo automático; stock_before=0. |
| `ADJUSTMENT_IN` | > 0 | Manual | USER autenticado, motivo requerido. |
| `ADJUSTMENT_OUT` | < 0 | Manual | USER autenticado, motivo requerido. |
| `PURCHASE_RECEIPT` | > 0 | Una línea de recepción | Operación de recepción, una vez por origen. |
| `SALE` | < 0 | Una línea de venta | Operación de venta, una vez por origen. |

Una apertura de corte puede tener delta 0; los ajustes con delta 0 no crean movimiento. Debe haber un solo origen de los grupos compra, venta o apertura/ajuste. Tipo, signo, actor y origen deben coincidir.

## Reservas, concurrencia y corte

Reservas activas siguen en `inventory_reservations`/`inventory_reservation_items`. Un ajuste bloquea el repuesto, obtiene el saldo y reservas y rechaza si el conteo físico queda por debajo de reservas. Las escrituras concurrentes se serializan por artículo; operaciones multiartículo conservan orden estable de locks.

El punto de corte conserva todas las filas históricas, registra una apertura SYSTEM por repuesto desde cero a `current_stock` bajo bloqueo de escrituras y permite reejecución sin duplicados. La apertura más reciente separa la historia legado de la nueva secuencia reconciliable; filas anteriores se muestran pero no vuelven a sumarse al saldo del corte.

## Retiro

Si hay movimientos, se marca `active=false`; no se borra la fila ni se pierde `spare_part_id`. La historia sigue consultable por el código. El borrado físico solo se conserva para artículos sin movimientos ni referencias históricas.
