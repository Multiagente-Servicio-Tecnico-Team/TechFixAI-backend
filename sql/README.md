# Base de datos

La base se instala con dos scripts, en este orden, sobre una base PostgreSQL **nueva** (16 o 17):

| Paso | Archivo | Qué hace |
| --- | --- | --- |
| 1 | `esquema-vacio-produccion.sql` | Crea el esquema completo: 41 tablas, tipos, índices, triggers y restricciones. No carga filas. |
| 2 | `seeds/datos-iniciales.sql` | Crea la cuenta ADMIN por defecto, carga 433 repuestos con su saldo inicial y el plan contable PCGE Perú Modificado 2019 (1192 cuentas). |

Los dos corren en una transacción: si algo falla, la base queda como estaba. Ya no hay migraciones incrementales; el esquema vigente es el del paso 1.

## 1. Crear la base y el esquema

```bash
createdb -U postgres multiagentedb
psql -U postgres -d multiagentedb -v ON_ERROR_STOP=1 -f sql/esquema-vacio-produccion.sql
```

No lo ejecutes sobre una base con datos que deban conservarse.

## 2. Cargar los datos iniciales

La contraseña del ADMIN no se guarda en el repositorio. Genera el hash bcrypt de la contraseña elegida desde el backend (cumple la política: 8 a 72 caracteres, una mayúscula, un número y un símbolo):

```bash
python -c "import getpass; from app.accounts.security import hash_password; print(hash_password(getpass.getpass('Contraseña: ')))"
```

En la **misma sesión** fija el hash (y, si quieres, otro correo; por defecto `admin@techfix.pe`) y ejecuta el seed. Con psql:

```bash
psql -U postgres -d multiagentedb -v ON_ERROR_STOP=1 \
  -c "SET techfix.admin_password_hash = '<hash bcrypt>'" \
  -c "SET techfix.admin_email = 'admin@techfix.pe'" \
  -f sql/seeds/datos-iniciales.sql
```

En pgAdmin: abre Query Tool sobre la base, ejecuta primero las dos líneas `SET ...;` y luego el contenido del archivo en la misma pestaña.

Sin el hash, el script se detiene con un mensaje y no guarda nada. Se puede repetir sin duplicar: no modifica al ADMIN si su correo ya existe, no pisa repuestos con el mismo código y el PCGE es idempotente.

## Verificar

Al terminar, el script muestra `Datos iniciales listos: 1 ADMIN, 433 repuestos, 1192 cuentas PCGE.` y aborta si falta algo. También puedes comprobarlo con:

```sql
SELECT (SELECT count(*) FROM users WHERE role = 'ADMIN') AS admins,
       (SELECT count(*) FROM spare_parts) AS repuestos,
       (SELECT count(*) FROM inventory_movements WHERE movement_type = 'OPENING_BALANCE') AS saldos_iniciales,
       (SELECT count(*) FROM accounting_accounts) AS cuentas_pcge;
```

## Notas

- Cada repuesto recibe un saldo inicial `SYSTEM` igual a su stock de carga, para que su historial de movimientos cuadre con `current_stock`.
- `account_group`, `normal_balance` e `is_postable` del PCGE son una clasificación inicial inferida, no una certificación del MEF; un contador debe validarlas antes de registrar operaciones reales. Fuente: https://www.mef.gob.pe/contenidos/conta_publ/documentac/PCGE_2019.pdf
- Los precios y existencias del inventario son datos de referencia para pruebas y demostración.
- Los códigos SKU usan solo mayúsculas, números y guiones, la misma regla que aplica el backend al crear o editar un repuesto.
- Un cambio de esquema se hace actualizando `esquema-vacio-produccion.sql` desde un `pg_dump --schema-only` y avisando al equipo.
