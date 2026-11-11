# Limpieza de tablas obsoletas

**Base:** `multiagentedb`, PostgreSQL local de pruebas  
**Fecha:** 2026-11-03  
**Migración:** `sql/migrations/010_remove_obsolete_tables.sql`

## Tablas retiradas

- `customer_commerce_migration_map`: mapa auxiliar del backfill 008; los vínculos resultantes ya viven en `customers.user_id` y `tickets.commercial_customer_id`. Antes de retirarlo se comprobó que el único mapeo seguía reconciliado.
- `customer_commerce_migration_issues`: tabla temporal de incidencias; estaba vacía y no había incidencias abiertas.
- `notification_history`: sin consumidor en el código de la aplicación y vacía. Se retiró también de la herramienta de limpieza puntual de tickets de prueba.

La migración falla si 009 no está registrada, quedan incidencias abiertas, el mapa no coincide con las relaciones comerciales actuales o `notification_history` contiene filas. Usa `DROP TABLE` sin `CASCADE` para no ocultar dependencias nuevas.

## Datos que se conservaron

Las tablas de cuentas, clientes, tickets, cotizaciones, líneas, pagos, inventario, garantías, logística, compras, ventas, auditoría y el ledger `schema_migrations` se conservaron. La verificación posterior confirmó los conteos previos de `users` (3), `customers` (1), `tickets` (4), `quotes` (1), `quote_details` (1), `payments` (2), `sales_orders` (0) y `spare_parts` (431).

Se creó y validó un respaldo PostgreSQL completo antes de la operación:

- Archivo local: `backups/customer-commerce-multiagentedb-pre-cleanup-2026-11-03.dump` (fuera del repositorio backend).
- SHA-256: `7d35a877b6a0ab7886afd4d40816a756c3ca2a116a576bf98567d10b6987402c`.

## Reconciliación pendiente del ledger

El ledger registró correctamente las migraciones 006–010. La utilidad reporta 003–005 como `UNRECORDED`, aunque sus tablas existen y la aplicación las usa. No se alteró ese estado ni se eliminaron esas tablas; hay que reconciliar esas versiones antes de confiar en que un despliegue reconstruido aplique una secuencia completa.
