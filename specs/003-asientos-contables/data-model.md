# Data Model: Asientos contables

El esquema se agrega con `sql/migrations/003_accounting_entries.sql`; no modifica ni recrea tablas comerciales existentes. Los importes de ejemplo/JSON se representan como cadenas, pero se validan y calculan como `Decimal`.

## `accounting_categories`

Catálogo interno para clasificación y filtros; no se presenta como un catálogo tributario de SUNAT.

| Campo | Tipo/constraint | Descripción |
|---|---|---|
| `id` | BIGINT identity PK | Identidad estable. |
| `code` | VARCHAR(40), UNIQUE, NOT NULL | Clave: `SALE`, `SERVICE`, `PURCHASE`, `OPERATING_EXPENSE`, `ADJUSTMENT`, `OTHER`. |
| `name` | VARCHAR(100), NOT NULL | Etiqueta en español para la vista. |
| `description` | TEXT, nullable | Ayuda corta de uso. |
| `active` | BOOLEAN, NOT NULL, default true | Solo activas aparecen para altas nuevas; no borra referencias históricas. |
| `created_at` | TIMESTAMPTZ, NOT NULL | Fecha UTC de alta. |

`accounting_entries.category_id` referencia la categoría con `ON DELETE RESTRICT`.

## `accounting_entries`

Encabezado inmutable de la operación. Solo `status` y las marcas de reversión pueden cambiar al producir una reversión; importes, fecha, concepto, categoría y líneas no se editan.

| Campo | Tipo/constraint | Descripción |
|---|---|---|
| `id` | BIGINT identity PK | ID API, nunca reemplaza el correlativo visible. |
| `entry_number` | BIGINT UNIQUE NOT NULL, global | Correlativo asignado por secuencia; único, monotónico en asignación y puede tener huecos. |
| `operation_date` | DATE NOT NULL | Fecha contable elegida por el `ADMIN`. |
| `concept` | VARCHAR(200) NOT NULL | Glosa/concepto breve. |
| `detail` | TEXT NOT NULL | Detalle de la operación. |
| `category_id` | BIGINT FK RESTRICT, NOT NULL | Categoría seleccionada. |
| `currency` | CHAR(3) NOT NULL, CHECK `PEN` | Moneda única de v1. |
| `debit_total` | NUMERIC(14,2) NOT NULL, CHECK > 0 | Total del debe, coincide con `credit_total`. |
| `credit_total` | NUMERIC(14,2) NOT NULL, CHECK > 0 | Total del haber y monto resumen. |
| `status` | VARCHAR/check: `CONFIRMED` o `REVERSED` | Todos los asientos nacen `CONFIRMED`; el original pasa a `REVERSED` al compensarse. |
| `responsible_user_id` | BIGINT FK `users(id)` RESTRICT, NOT NULL | Cuenta `ADMIN` derivada de sesión; no del body. |
| `idempotency_key` | UUID, nullable en reversiones internas | Clave del alta para reintentos del endpoint de creación. |
| `request_hash` | CHAR(64), nullable en reversiones internas | SHA-256 del payload canónico; detecta reutilización incorrecta de clave. |
| `reversal_of_entry_id` | BIGINT FK a misma tabla RESTRICT, nullable, UNIQUE | Apunta desde la reversión al original y evita más de una reversión. No se permiten autociclos. |
| `reversal_reason` | TEXT, nullable | Requerido si `reversal_of_entry_id` no es null. |
| `created_at` | TIMESTAMPTZ, NOT NULL | Momento UTC de registro. |
| `updated_at` | TIMESTAMPTZ, NOT NULL | Momento UTC del último cambio de estado; inicialmente coincide con `created_at`. |
| `reversed_at` | TIMESTAMPTZ, nullable | Momento UTC en que el original fue revertido. |

Restricciones/índices adicionales: UNIQUE `(responsible_user_id, idempotency_key)`; índice por `(operation_date DESC, entry_number DESC)`, `category_id`, `status`, y `responsible_user_id`. Un trigger impide referencia de reversión a sí misma. La unicidad global es del correlativo; no se requiere secuencia sin huecos.

La respuesta del original incluye `reversal_entry_id` derivado de la fila reversa; la respuesta de la reversión incluye `reversal_of_entry_id` persistido. No se duplica el vínculo en ambas filas.

## `accounting_entry_lines`

Snapshot de una línea dentro de un asiento. No depende de que se haya cargado un plan de cuentas oficial.

| Campo | Tipo/constraint | Descripción |
|---|---|---|
| `id` | BIGINT identity PK | Identidad. |
| `entry_id` | BIGINT FK `accounting_entries(id)` RESTRICT, NOT NULL | Asiento padre; las líneas no se borran por eliminación accidental del encabezado. |
| `line_number` | SMALLINT NOT NULL | Orden desde 1; UNIQUE `(entry_id, line_number)`. |
| `account_code` | VARCHAR(40) NOT NULL | Código introducido por el `ADMIN`; no validado contra PCGE oficial. |
| `account_name` | VARCHAR(200) NOT NULL | Denominación introducida; queda como snapshot histórico. |
| `description` | TEXT nullable | Detalle opcional por línea. |
| `debit` | NUMERIC(14,2) NOT NULL DEFAULT 0, CHECK >= 0 | Importe de debe. |
| `credit` | NUMERIC(14,2) NOT NULL DEFAULT 0, CHECK >= 0 | Importe de haber. |

Check por fila: exactamente uno de `debit`, `credit` debe ser mayor que cero. Debe haber como mínimo dos líneas y suma debit = suma credit = totales del encabezado. Esta última regla es inter-filas: se valida en dominio y con constraint trigger diferido al fin de transacción, no con un `CHECK` que consulte otras filas.

## `accounting_audit_events`

Historial append-only de acciones. La creación registra `ENTRY_CREATED`; una reversión registra `ENTRY_REVERSED` para el original y `REVERSAL_CREATED` para el nuevo asiento, con referencias cruzadas y la razón.

| Campo | Tipo/constraint | Descripción |
|---|---|---|
| `id` | BIGINT identity PK | Orden estable de evento. |
| `entry_id` | BIGINT FK `accounting_entries(id)` RESTRICT, NOT NULL | Asiento observado. |
| `actor_user_id` | BIGINT FK `users(id)` RESTRICT, NOT NULL | `ADMIN` de sesión que ejecuta la acción. |
| `event_type` | VARCHAR/check | `ENTRY_CREATED`, `ENTRY_REVERSED`, `REVERSAL_CREATED`. |
| `related_entry_id` | BIGINT FK a `accounting_entries(id)` RESTRICT, nullable | Original/reversión enlazada. |
| `reason` | TEXT nullable | Razón para evento de reversión. |
| `created_at` | TIMESTAMPTZ, NOT NULL | Fecha/hora UTC. |

UNIQUE/append-only según el evento y permisos de la API: no hay rutas para alterar o eliminar eventos. Índice `(entry_id, created_at, id)` para mostrar cronología.

## Estados y transacciones

- Alta: valida sesión/rol, categoría, líneas, cantidades y balance; persiste encabezado `CONFIRMED`, líneas, clave idempotente y `ENTRY_CREATED` en una transacción.
- Reintento de alta con actor y key iguales: mismo hash devuelve el resultado existente. Hash distinto devuelve `409` sin crear otro asiento.
- Reversión: bloquea el original para serializar competidores, valida `CONFIRMED` y ausencia de reversión, inserta la reversión confirmada con debit/credit intercambiados, marca original `REVERSED` e inserta ambos eventos en la misma transacción. Un reintento con los mismos datos devuelve la reversión existente; una petición con razón/fecha diferente recibe conflicto.
- Error durante cualquier escritura: rollback completo del encabezado, líneas y auditoría. Un valor de secuencia puede quedar consumido; no se promete correlativo sin huecos.
- Borrado/desactivación de usuario/categoría: `RESTRICT`; la auditoría histórica no puede quedar huérfana. La categoría puede inactivarse sin borrarse.
