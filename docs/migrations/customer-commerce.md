# Operación de esquema: clientes comerciales

## Estado inicial

La base local `multiagentedb`, inspeccionada en modo de solo lectura el 2026-11-03, no tiene `customers` ni ledger `schema_migrations`. `tickets.customer_id` y `payments.customer_id` referencian `users`; `quotes.ticket_id` es requerido. `ticket_audit_events.ticket_id` usa `ON DELETE RESTRICT`; tickets/quotes/payments tienen otras dependencias que se deben verificar contra el catálogo vivo antes de operar.

## Estado tras la ejecución autorizada

El 2026-11-03 se aplicaron y registraron las migraciones 006–009 en la base de prueba `multiagentedb`. Los checksums del ledger coinciden con los archivos SQL vigentes. La base tenía 3 cuentas, 12 tickets, 3 cotizaciones y 6 pagos; después quedó con 3 cuentas, 1 perfil comercial, 4 tickets de servicio, 1 cotización de servicio y 2 pagos. El backfill creó un perfil vinculado a la cuenta propietaria de los registros y no reportó incidencias sin resolver.

El respaldo custom-format se guardó en `backups/customer-commerce-multiagentedb-before-007.dump` desde la raíz compartida del workspace; el archive fue validado con `pg_restore --list`. El informe de limpieza registra el SHA-256, las filas eliminadas y los conteos finales.

## Aplicación

1. Respaldo creado y archive listado para validación; no se ha probado una restauración física en otra base.
2. Las migraciones 003–005 no se registraron retroactivamente; el ledger contiene solo 006–009, que sí se ejecutaron y verificaron.
3. Migraciones 006–009 aplicadas en orden. Se crearon customers y las tablas de reservas/ventas.
4. Backfill por usuario legado aplicado; 1 perfil portal, 12 tickets mapeados antes de la limpieza y cero incidencias pendientes.
5. Columnas legacy conservadas para compatibilidad.
6. Constraints finales aplicadas; sin customer IDs nulos ni desajustes entre tickets y cotizaciones.
7. Fixture exacto limpiado mediante el manifiesto aprobado, no desde el proceso web. El detalle está en el reporte de limpieza.

## Filas `SALE` de prueba

La limpieza cubrió únicamente los ocho IDs del manifiesto aprobado y sus dependientes verificados. No se usó un filtro genérico por tipo. El resultado está en [`007-sale-test-fixture-cleanup.md`](007-sale-test-fixture-cleanup.md).
