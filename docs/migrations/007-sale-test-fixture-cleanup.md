# Limpieza ejecutada: fixture SALE de prueba

## Destino y alcance

- Base de prueba: `multiagentedb`.
- Fecha del snapshot del manifiesto: 2026-11-03.
- Ocho tickets autorizados: IDs 3, 4, 7, 8, 9, 10, 11 y 12.
- El manifiesto JSON aprobado se utilizo durante esa ejecucion, pero no se conserva en este repositorio.
- Ejecución transaccional después de migración 008 y antes de migración 009, el 2026-11-03, entre 20:31:04 y 20:31:41 (hora local America/Bogota).

## Resultado de preflight

Se comprobó que los ocho IDs todavía existen y todos tienen tipo `SALE`. Los dependientes actuales coinciden exactamente con el manifiesto:

| Tabla | Filas asociadas |
| --- | ---: |
| tickets | 8 |
| logistics_records | 4 |
| payments | 4 |
| quotes | 2 |
| quote_details | 2 |
| warranties | 3 |
| refunds | 0 |
| ticket_audit_events | 0 |
| notification_history | 0 |
| warranty_claims | 0 |

El preflight coincidió exactamente con el manifiesto. Los cuatro pagos estaban pendientes; se eliminaron únicamente por ser dependientes directos de estos tickets de prueba, no se marcaron como pagados.

## Filas eliminadas

| Tabla | Antes | Eliminadas | Después |
| --- | ---: | ---: | ---: |
| tickets | 8 | 8 | 0 |
| logistics_records | 4 | 4 | 0 |
| payments | 4 | 4 | 2 en total |
| quotes | 2 | 2 | 1 en total |
| quote_details | 2 | 2 | se conserva la única línea de la cotización de servicio |
| warranties | 3 | 3 | 0 ligadas al fixture |
| refunds | 0 | 0 | 0 |
| ticket_audit_events | 0 | 0 | 0 |
| notification_history | 0 | 0 | 0 |
| warranty_claims | 0 | 0 | 0 |

El sistema quedó con 4 tickets de servicio (2 PC_BUILD, 2 SUPPORT), 1 cotización de servicio, 2 pagos y 0 tickets SALE. Se conservaron las 3 cuentas de usuario. Las migraciones 006–009 están aplicadas y registradas.

## Respaldo

- Archivo: `C:\Users\josep\Downloads\Taller\backups\customer-commerce-multiagentedb-before-007.dump`
- Formato custom de PostgreSQL; `pg_restore --list` verificó que el archivo se puede leer. No se hizo una restauración física en otra base.
- Tamaño: 130946 bytes.
- SHA-256: `D53497A6C1FD21307B5BC988D85C6DAA328283024264C565CFA13E982A96B5BA`

## Estado del artefacto de limpieza

El script y el manifiesto fueron herramientas de una sola ejecucion y ya no estan en el repositorio. Este archivo es un reporte historico, no un procedimiento repetible. No intentes reconstruir el manifiesto ni volver a borrar registros usando esos IDs. La prueba unitaria que importaba el script eliminado tambien fue reemplazada por una comprobacion de este reporte.
