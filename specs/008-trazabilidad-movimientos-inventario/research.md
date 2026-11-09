# Research: Trazabilidad de movimientos de inventario

**Feature**: [spec.md](spec.md)  
**Fecha**: 2026-11-08

## Alcance revisado

Se revisaron la especificación y OpenAPI de `specs/005-api-inventario`, rutas y persistencia de inventario, compras y ventas, sesión/roles, errores, pruebas y `sql/esquema-vacio-produccion.sql`. No se consultó una BD remota, no se hicieron escrituras y no se ejecutaron pruebas.

## Hallazgos

- `app/adapters/api/inventory.py`: GET/listado, alta, PUT y DELETE; el esquema de alta/edición recibe `current_stock`.
- `app/adapters/persistence/inventory.py`: crea y actualiza existencias directamente. En PUT bloquea el repuesto y evita bajar del stock reservado, pero no crea movimiento.
- `app/adapters/persistence/purchases.py`: la recepción aumenta stock e inserta `PURCHASE_RECEIPT` por línea dentro de la transacción; tiene `Idempotency-Key` y hash.
- `app/adapters/persistence/sales_quotes.py`: la confirmación de venta disminuye stock e inserta `SALE` por línea en la misma transacción; el origen y la clave de pago previenen duplicados.
- La búsqueda de escrituras en Python encontró esos caminos (catálogo, recepción y venta); la implementación repetirá el inventario de escrituras antes de modificar.
- `inventory_movements` guarda `spare_part_id`, orígenes de línea de compra/venta, tipo, snapshots de SKU/nombre, delta, saldo antes/después, `actor_user_id` y fecha. Las restricciones solo permiten tipos `PURCHASE_RECEIPT`/`SALE`, delta no cero y XOR entre esos dos orígenes. FK actor RESTRICT; FK repuesto SET NULL; unicidad por línea origen.
- Reservas viven en `inventory_reservations` / `inventory_reservation_items`; un ajuste no puede reducir stock por debajo de reservas activas.
- `require_staff` autoriza `ADMIN`/`TECHNICIAN`; clientes reciben 403. Se conserva cookie de sesión.
- Pruebas existentes: `tests/contract/test_inventory_contract.py`, `tests/integration/test_inventory_api.py`. Se ampliarán en implementación; aquí no se crean ni ejecutan.
- El checkout actual no tiene `sql/migrations/`; `sql/esquema-vacio-produccion.sql` es bootstrap, no migración. El script `contexto/tablas postgres v2.sql` reconstruye el esquema y no se usará para migrar.

## Comparación con la BD de prueba (solo lectura, 2026-11-08)

La conexión cargada desde el `.env` del backend llegó a la BD `multiagentedb` usando una transacción `READ ONLY`. Las columnas de `spare_parts`, `inventory_movements`, `inventory_reservations`, `inventory_reservation_items`, `purchase_receipt_items`, `sales_order_items` y `users` coinciden con `sql/esquema-vacio-produccion.sql`; no hubo columnas faltantes ni adicionales. Las constraints revisadas de movimientos también coinciden con el dump: solo acepta `PURCHASE_RECEIPT`/`SALE`, delta no nulo y origen XOR de recepción/venta.

Conteos agregados consultados: 431 repuestos, todos con stock positivo; suma de 2,618 unidades; 1 movimiento previo; 0 reservas activas. No se leyeron filas de cliente/usuario ni se cambió la base. El corte necesita crear una apertura inicial por artículo (431 según el estado observado) y preservar el único movimiento anterior como historia legado. Los conteos pueden cambiar antes de implementar; la migración debe calcularlos al ejecutarse y no codificar estos números.
## Decisiones

### D1. Regla única para aplicar cambios de stock
**Decisión**: Centralizar en una función de persistencia que se ejecuta dentro de la transacción del caller: validar saldo/reservas, actualizar el saldo e insertar un movimiento. La comparten ajuste, recepción y venta.
**Razón**: Evita que varias rutas de escritura mantengan invariantes diferentes.
**Alternativa descartada**: Repetir SQL y depender solo de pruebas.

### D2. El CRUD no modifica stock
**Decisión**: Alta nueva parte en cero y PUT no cambia el saldo directamente. Para mantener compatibilidad con el frontend actual, `current_stock` queda opcional y obsoleto durante la transición; si se recibe, backend lo traduce dentro de la misma transacción a una apertura/ajuste auditable con actor de sesión y motivo fijo de compatibilidad. Las nuevas rutas explícitas reciben conteo físico y motivo, y el backend calcula el delta.
**Razón**: Stock es un saldo operacional y requiere actor, intención y repetición segura.
**Alternativa descartada**: Movimiento implícito dentro del PUT, que no registra motivo ni expresa una operación idempotente.

### D3. Orígenes y tipos
**Decisión**: Conservar `PURCHASE_RECEIPT`/`SALE`, añadir `OPENING_BALANCE`, `ADJUSTMENT_IN`, `ADJUSTMENT_OUT`; conservar FKs de compras/ventas y representar entradas manuales/corte explícitamente en movimiento.
**Razón**: Signos y orígenes se pueden validar sin FK polimórfica libre.
**Alternativa descartada**: Campo genérico tipo/id sin referencialidad.

### D4. Autoría e idempotencia
**Decisión**: Actor humano sale de sesión. Aperturas/ajustes requieren motivo y `Idempotency-Key` con hash del payload. El corte usa actor `SYSTEM` identificable, sin usuario ficticio.
**Razón**: Respeta seguridad/autoría y reutiliza patrón de recepciones.
**Alternativa descartada**: Crear una cuenta sintética o aceptar actor/delta del solicitante.

### D5. Corte de saldos existentes
**Decisión**: Preservar eventos antiguos y tomar bajo bloqueo un saldo inicial por repuesto con `OPENING_BALANCE` SYSTEM desde cero. El corte marca comienzo de la secuencia reconciliable; eventos anteriores se conservan como historia legado y no se suman de nuevo. Permitir evento de corte cero.
**Razón**: No se pueden reconstruir con certeza movimientos previos omitidos.
**Alternativas descartadas**: Inventar documentos históricos o impedir toda trazabilidad nueva hasta reconstruirlos.

### D6. Retiro y consultas
**Decisión**: Retirar artículos con movimientos como inactivos, no borrar físicamente; historial interno paginado y filtrado por tipo/fecha para ADMIN/TECHNICIAN.
**Razón**: El esquema ya dispone de `active` y de snapshots.
**Alternativa descartada**: Desvincular `spare_part_id` y dejar solo snapshots.

### D7. Migración y documentación
**Decisión**: Crear migración SQL incremental, versionada, transaccional y reejecutable bajo `sql/migrations/`; actualizar `sql/esquema-vacio-produccion.sql` solo para nuevas BD.
**Razón**: No existe directorio de migraciones en este checkout y el script de bootstrap no es una migración.
**Alternativa descartada**: Aplicar un dump destructivo en una BD con datos.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Otra ruta modifica stock | Búsqueda transversal y operación común de persistencia. |
| Corte concurre con compra/venta | Serializar escrituras durante corte y verificar con PostgreSQL. |
| Conteo deja reservas sin cubrir | Bloquear repuesto y rechazar atómicamente si conteo < reserva activa. |
| Retry duplica stock | Clave+hash y respuesta de replay; orígenes actuales mantienen unicidad. |
| Esquema objetivo difiere del dump | Comparar BD destino con requisitos antes de ejecutar la futura migración. |

No quedan decisiones de negocio bloqueantes para el diseño. La versión del esquema destino se debe verificar antes de implementación/despliegue; este plan no inspeccionó una BD remota.

