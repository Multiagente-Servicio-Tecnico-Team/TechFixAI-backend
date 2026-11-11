# API de inventario del taller

**Estado**: CRUD y trazabilidad de movimientos implementados en backend.
**Spec Kit**: `specs/005-api-inventario/` y `specs/008-trazabilidad-movimientos-inventario/`.
**Contratos**: `specs/005-api-inventario/contracts/inventory.openapi.yaml` y `specs/008-trazabilidad-movimientos-inventario/contracts/inventory-movements.openapi.yaml`.

## Rutas

| Método y ruta | Resultado |
|---|---|
| `GET /api/inventory/parts` | Lista repuestos activos como `{ "parts": [...] }`. |
| `GET /api/inventory/categories` | Lista categorías distintas de repuestos activos como `{ "categories": [...] }`. |
| `POST /api/inventory/parts` | Crea un repuesto activo; devuelve 201 y `{ "part": ... }`. |
| `PUT /api/inventory/parts/{code}` | Reemplaza los datos editables; devuelve 200 y `{ "part": ... }`. El código no se puede cambiar. |
| `DELETE /api/inventory/parts/{code}` | Elimina si es posible; devuelve 204 sin cuerpo. Si un presupuesto lo referencia, devuelve 409 `in_use`. |
| `POST /api/inventory/parts/{part_id}/opening-balance` | Registra conteo inicial con motivo y `Idempotency-Key`; no admite sobrescribir un saldo existente. |
| `POST /api/inventory/parts/{part_id}/adjustments` | Ajusta al conteo físico. El backend calcula el delta, verifica reservas y registra actor/motivo. Un conteo igual no crea movimiento. |
| `GET /api/inventory/parts/{part_id}/movements` | Lista historial paginado (máximo 200), ordenado por fecha e ID descendentes; filtros: tipo y fechas `from_date`/`to_date`. Incluye actor, motivo, origen y marca pre-corte. |

## Órdenes de compra a proveedores

Las rutas requieren sesión ADMIN y usan el esquema de migración 014. La orden no reserva ni cambia stock. El incremento ocurre únicamente al confirmar una recepción física; cada línea catalogada crea su movimiento transaccional e idempotente.

| Método y ruta | Resultado |
|---|---|
| `GET /api/admin/purchase-orders` | Lista paginada; filtros opcionales `supplier_id`, `status`, `date_from`, `date_to`; límite máximo 100. |
| `POST /api/admin/purchase-orders` | Crea borrador con proveedor y líneas de catálogo o texto libre; calcula totales y guarda snapshots. No cambia stock. |
| `GET /api/admin/purchase-orders/{order_id}` | Devuelve orden, cantidades pedidas/recibidas/pendientes/facturadas/canceladas, comprobantes vinculados, recepciones y auditoría. |
| `PATCH /api/admin/purchase-orders/{order_id}` | Edita únicamente borradores. |
| `POST /api/admin/purchase-orders/{order_id}/issue` | Emite un borrador; registra usuario y fecha. |
| `POST /api/admin/purchase-orders/{order_id}/cancel` | Cancela cantidades pendientes con motivo obligatorio; conserva recepciones y movimientos ya registrados. |
| `POST /api/admin/purchase-orders/{order_id}/receipts` | Confirma recepción parcial o completa. Requiere `Idempotency-Key` UUID; un reintento idéntico devuelve la recepción existente. |
| `GET /api/admin/purchase-orders/{order_id}/receipts` | Lista las recepciones, responsables y movimientos asociados. |

Los comprobantes de proveedor siguen siendo documentos separados. Si `purchase_order_id` está informado, las líneas pueden mapearse mediante `purchase_order_item_id` para informar cantidades facturadas. Su endpoint de recepción devuelve 409 para órdenes vinculadas; la entrada física debe registrarse una sola vez desde la ruta de recepciones de la orden. La migración 014 está versionada, requiere preflight y no se ejecuta automáticamente; véase `sql/migrations/README.md`.

Las rutas de inventario requieren la cookie `techfix_session` y aceptan roles `ADMIN` y `TECHNICIAN`. Una sesión inválida devuelve 401; un cliente devuelve 403. Las rutas de órdenes de compra de la sección anterior requieren rol `ADMIN`.

## Datos y compatibilidad

- El catálogo usa `spare_parts`; toda variación posterior de stock actualiza `spare_parts.current_stock` e inserta `inventory_movements` dentro de una única transacción.
- El precio se recibe y devuelve como texto decimal de dos posiciones y se persiste sin conversiones a float.
- El código sigue el formato de SKU que valida el formulario actual. El mínimo es entero de 0 a 999999. El alta inicia con saldo cero y el CRUD no cambia directamente el stock.
- Compatibilidad temporal: el backend todavía acepta `current_stock` opcional del formulario frontend existente y lo convierte en apertura/ajuste auditable con actor autenticado y motivo de transición. Está marcado obsoleto en OpenAPI; las nuevas integraciones deben usar las rutas dedicadas.
- La migración `sql/migrations/20261108_inventory_movement_traceability.sql` preserva movimientos previos y registra una apertura SYSTEM por artículo como punto de corte. Se aplicó a la base local de prueba `multiagentedb` y se registró como versión `011`; no se aplicó a producción. El bootstrap `sql/esquema-vacio-produccion.sql` refleja el esquema final.
- Artículos con movimientos o reservas se retiran como inactivos en lugar de borrarse físicamente; el historial sigue consultable por ID.
- La recepción de compras y la confirmación de ventas llaman al escritor transaccional compartido; conserva sus vínculos de origen e idempotencia de cada operación de negocio.
- Las categorías se conservan tal como están en la base. La ruta de categorías permite cubrir valores fuera de las cinco opciones fijas que la interfaz muestra hoy.
- El origen del frontend debe estar en `FRONTEND_ORIGINS`. CORS incluye `PUT`, necesario para el formulario de edición.
- La FK `quote_details.spare_part_id` conserva el historial: una referencia impide eliminar el repuesto. La FK de `purchase_order_items` mantiene su regla existente `ON DELETE SET NULL`.

## Verificación

No se ejecutaron pruebas automatizadas ni llamadas HTTP de extremo a extremo. La migración se verificó en PostgreSQL local: 431 artículos recibieron 431 saldos de corte SYSTEM (2,618 unidades), y el movimiento legado quedó preservado. Antes de usar otra base, aplicar ahí la migración en una ventana con las escrituras de stock detenidas. La guía manual está en `specs/008-trazabilidad-movimientos-inventario/quickstart.md`.

## Limitación frontend pendiente

El frontend puede continuar con el campo `current_stock` mientras integra apertura, ajustes e historial. Después de esa integración debe dejar de enviarlo en el CRUD y consumir las nuevas rutas de movimientos.
