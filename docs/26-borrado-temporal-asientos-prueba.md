# Borrado temporal de asientos de prueba

**Base autorizada:** `multiagentedb`, local de pruebas  
**Estado:** guardas de inmutabilidad deshabilitadas temporalmente a solicitud del usuario. No se borraron filas.  
**Fecha:** 2026-11-03

## Guardas temporalmente deshabilitadas

- `accounting_entries_immutable` en `accounting_entries`.
- `accounting_lines_immutable` en `accounting_entry_lines`.
- `accounting_audit_append_only` en `accounting_audit_events`.

Se conservaron activos los triggers de balance y las 7 claves foráneas de esas tablas. Por eso, pgAdmin puede seguir rechazando un DELETE de un padre mientras haya filas relacionadas. Eliminar datos asociados requiere borrar solo los registros de prueba, en orden de dependencias; si hay asiento de reversión, se elimina primero el asiento de reversión.

## Cómo restaurar las guardas

Después de terminar la limpieza, ejecutar `sql/operations/accounting-test-triggers-restore.sql` conectado a `multiagentedb`. El script verifica que se trata de esa base y que las tres guardas están deshabilitadas antes de habilitarlas. No reutilizar este procedimiento en producción.

## Respaldo previo

- Archivo local: `backups/multiagentedb-before-temporary-accounting-trigger-disable-2026-11-03.dump` (fuera del repositorio backend).
- SHA-256: `70763fdcb9a9743f1571033acf1a65437063309b2a48cb1c9e3322e3e892e3ae`.
- `pg_restore --list` confirmó que es un respaldo custom de `multiagentedb`.
