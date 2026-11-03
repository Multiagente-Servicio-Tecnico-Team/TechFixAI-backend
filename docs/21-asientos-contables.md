# Registro interno de asientos contables

## Alcance implementado

- Endpoints bajo `/api/admin/accounting`: categorias, alta, listado paginado con filtros, detalle y reversion.
- Todas las rutas requieren sesion vigente `ADMIN`. El responsable se deriva de la sesion autenticada.
- Los asientos se confirman al crearlos, en PEN, con lineas debe/haber balanceadas e idempotencia por actor y UUID.
- Los asientos confirmados no se editan ni eliminan. La correccion se registra como asiento inverso y eventos de auditoria.
- La API entrega importes como texto con dos decimales y no registra operaciones desde el chat o los agentes.
- Las categorias son internas; los codigos de cuenta no se certifican contra un PCGE oficial. No se genera ni presenta PLE.

## Archivos

- `app/domain/accounting.py`: validaciones de montos, lineas, fechas y balance.
- `app/application/accounting.py`, `app/application/ports.py`, `app/application/errors.py`: casos de uso, contrato de persistencia y errores seguros.
- `app/adapters/api/accounting.py`: DTOs y rutas HTTP.
- `app/adapters/persistence/accounting.py`: transacciones, consultas y auditoria PostgreSQL.
- `sql/migrations/003_accounting_entries.sql`: migracion aditiva, restricciones, indices y triggers.

## Trazabilidad de base de datos

**Estado: aplicada y verificada en la base de prueba `multiagentedb` el 2026-11-02.** Antes de migrar se observaron 15 tablas y 30 indices; no existian tablas `accounting_*`. Despues quedaron 19 tablas y 46 indices. Se anadieron `accounting_categories`, `accounting_entries`, `accounting_entry_lines` y `accounting_audit_events`, junto con seis categorias iniciales. Las tablas comerciales existentes permanecieron presentes; la migracion fue aditiva y transaccional.

La verificacion Quickstart creo un asiento y su reversion (IDs 19 y 20), comprobo replay idempotente, rechazo 422 de entrada invalida y 401 sin sesion. La prueba PostgreSQL de concurrencia creo otro asiento y reversion (IDs 17 y 18), confirmando que solo una reversion gana la carrera. La cuenta ADMIN sintetica utilizada por las pruebas quedo desactivada; la FK y la auditoria append-only impiden borrar esos registros con seguridad. El total final es cuatro asientos (dos originales revertidos y dos inversos), ocho lineas y seis eventos de auditoria. No se alteraron tablas de clientes, pagos, cotizaciones ni inventario. No se guardaron URLs, credenciales ni datos personales.

La base contiene datos sinteticos permanentes de esta validacion. No usarla como base limpia para pruebas que asuman tablas contables vacias; usar otra base aislada o fixtures propios.

## Validacion de codigo

- Pruebas focalizadas de dominio, aplicacion, adaptador, API, sesion y contrato: 39 aprobadas; tres pruebas PostgreSQL se omiten si no se configura `ACCOUNTING_TEST_DATABASE_URL`.
- Pruebas PostgreSQL con conexion explicita a la BD de prueba: 4 aprobadas, incluidas migracion, balance diferido, rollback y reversion concurrente.
- Quickstart HTTP contra la BD de prueba: alta 201, replay idempotente, detalle/listado/categorias 200, reversion y replay correctos, entrada invalida 422 y falta de sesion 401.
- Suite restante: 454 aprobadas, 3 omitidas y 1 seleccionada fuera; pruebas que usan `tmp_path` se excluyeron por ACL de temporales de Windows. Dos advertencias de dependencias.
- `python -m compileall -q app`: aprobado.
- `git diff --check`: aprobado; solo avisos LF/CRLF en archivos preexistentes ajenos a esta feature.
