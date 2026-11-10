# Seeds de catálogos

## PCGE Modificado 2019

`pcge_modificado_2019.sql` carga el plan `PCGE_PE` como predeterminado y sus 1.192 cuentas.

### Requisitos

- Base de datos con el esquema contable de la migración `012_accounting_catalog_schema.sql`.
- Al menos una cuenta `ADMIN` ya creada en `public.users`; se usa como autor del plan, las cuentas y el evento de auditoría.
- Ejecutar conectado explícitamente a la base destino correcta. El script no crea usuarios ni registra por sí mismo una versión en `schema_migrations`.

### Ejecución y verificación

En pgAdmin, abre Query Tool sobre la base destino y ejecuta el archivo completo. El bloque usa una transacción: ante un error, PostgreSQL revierte la carga. No ejecutes a la vez este seed y `013_seed_pcge_modificado_2019.sql`.

Verifica el resultado:

```sql
SELECT p.code, p.edition, p.name, p.is_default, COUNT(a.id) AS account_count
FROM public.accounting_plans p
LEFT JOIN public.accounting_accounts a ON a.plan_id = p.id
WHERE p.code = 'PCGE_PE' AND p.edition = 'Modificado 2019'
GROUP BY p.id, p.code, p.edition, p.name, p.is_default;
```

Debe devolver una fila con `is_default = true` y `account_count = 1192`.

Después de verificar que el esquema y el catálogo quedaron correctos, registra la migración 013 en el ledger desde el backend:

```powershell
python -m app.database.migrations record --version 013 --verified-by "Nombre del operador" --confirm-applied
```

Ese comando solo registra la versión; no ejecuta SQL. Asegúrate de que la configuración de conexión del backend apunte a la misma base que verificaste en pgAdmin.

El archivo no carga categorías contables ni asientos. `account_group`, `normal_balance` e `is_postable` son clasificaciones iniciales inferidas, no una certificación del MEF; valida esas propiedades con un contador antes de usar el plan en operaciones reales.
