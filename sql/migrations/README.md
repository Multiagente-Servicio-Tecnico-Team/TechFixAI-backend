# Migraciones PostgreSQL

Los archivos numerados describen cambios versionados; su presencia en Git no prueba que estén aplicados a una base. Antes de aplicar un archivo:

1. Confirma el destino y toma un respaldo restaurable.
2. Inspecciona `schema_migrations` y el catálogo PostgreSQL. Si no existe ledger, reconcilia manualmente el estado y registra únicamente versiones verificadas.
3. Revisa el SQL completo, calcula su SHA-256 y compáralo con el ledger.
4. Aplica primero en una copia aislada y verifica constraints, FKs, conteos e invariantes.
5. Registra la versión con la utilidad `python -m app.database.migrations record --version NNN --verified-by <operador> --confirm-applied` solo después de confirmar la aplicación correcta.

La utilidad no ejecuta SQL de migración. Las operaciones destructivas en `sql/operations/` son independientes, requieren destino de prueba, manifiesto exacto y backup, y no se incluyen en este procedimiento general.
