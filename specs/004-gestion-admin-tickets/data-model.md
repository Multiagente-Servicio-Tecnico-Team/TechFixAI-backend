# Data Model: Gestión administrativa de tickets

La migración propuesta es `sql/migrations/004_admin_ticket_management.sql`. Será aditiva respecto a las filas existentes y se ejecutará únicamente de forma explícita en una base de prueba. No se cambia `request_type_enum`: ya contiene los tipos que usará el formulario.

## `tickets` (extensión)

| Campo | Tipo/validación | Uso |
|---|---|---|
| `customer_id` | BIGINT FK `users(id)` RESTRICT, nullable | Obligatorio para `ONLINE`; opcional para ticket `MANUAL`. Su valor nunca se toma como identidad online del body. |
| `origin` | VARCHAR/check `MANUAL`, `ONLINE`; nullable solo en filas históricas | Canal de entrada. Para toda alta nueva la API exige un valor. Las filas antiguas se dejan desconocidas, no se infiere su origen. |
| `contact_name` | VARCHAR(200), nullable según origen | Nombre capturado para ticket manual; obligatorio en manual. En online se presenta desde el perfil asociado. |
| `contact_phone` | VARCHAR(20), nullable según origen | Teléfono capturado; obligatorio en manual. |
| `contact_email` | VARCHAR(255), nullable | Correo de contacto manual opcional; correo de cuenta online se obtiene del usuario. |
| `advance_amount` | NUMERIC(10,2), nullable, CHECK > 0 si no es null | Adelanto informado/cobrado al ingreso; no es el total de cotización ni se convierte por sí solo en una fila `payments`. |
| `advance_payment_method` | VARCHAR/check `YAPE_PLIN`, `CASH`, `CARD`, nullable | Método del adelanto manual. Requerido si existe importe; ambos campos quedan null si no se registró adelanto. |

Reglas por origen: `MANUAL` requiere `contact_name` y `contact_phone`, permite `customer_id` null y correo null. `ONLINE` requiere `customer_id`; los datos se presentan desde `users`. La aplicación debe escribir `origin` en todas las nuevas rutas. Las filas preexistentes conservan `origin = NULL` hasta que exista evidencia para clasificarlas.

Los campos existentes se mantienen: `title` recibe el texto único de “Equipo / Marca y Modelo”; `failure_description` recibe “Detalle de la Falla o Solicitud”; `request_type` recibe el código canónico del selector.

## `ticket_audit_events` (nueva)

| Campo | Tipo/validación | Uso |
|---|---|---|
| `id` | BIGINT identity PK | Orden del evento. |
| `ticket_id` | BIGINT FK `tickets(id)` RESTRICT, NOT NULL | Ticket afectado. |
| `actor_user_id` | BIGINT FK `users(id)` RESTRICT, NOT NULL | Actor de sesión: ADMIN para mantenimiento, cuenta autenticada para altas online. |
| `event_type` | CHECK: `CREATED`, `UPDATED`, `STATUS_CHANGED`, `CANCELLED`, `QUOTE_CREATED` | Tipo de operación sin guardar texto libre de request. |
| `changed_fields` | JSONB nullable | Lista de nombres de campos y, para estado, valores anterior/nuevo; no incluir contraseñas, sesión ni detalle personal innecesario. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP | Fecha del evento. |

Los eventos son append-only desde la API. Actualización de ticket y su evento se persisten en una única transacción. No se inventa auditoría para filas anteriores a la migración.

## `quotes` (reutilizada)

El esquema ya tiene `ticket_id NOT NULL`, `quote_type`, `labor_cost`, `parts_cost`, `total_amount` y `status`. Se crea la cotización posteriormente con estado `PENDING`; su `total_amount` es el costo total y no reemplaza `tickets.advance_amount`. La nueva operación de cotización valida que el ticket exista y no esté cancelado, calcula importes en `Decimal` y no inserta `payments` automáticamente. `quote_details` conserva las líneas si se usan artículos de inventario.

## `payments` (sin cambio en esta feature)

No se altera `payments.customer_id NOT NULL`, su enum de métodos ni sus estados. El adelanto administrativo del formulario se conserva en el ticket como solicitó el producto; el campo no implica creación o confirmación automática de una transacción en `payments`. Los flujos de pago existentes de usuarios permanecen separados.

## Relaciones y ciclo de vida

- Un ticket `ONLINE` pertenece a un usuario y aparece en su endpoint de tickets propios.
- Un ticket `MANUAL` pertenece al libro de trabajo del ADMIN; no aparece en `/api/customer/tickets` si no tiene cuenta asociada.
- Un ticket puede tener una o más cotizaciones; cada cotización referencia el ticket.
- Un ticket puede tener eventos de auditoría; se prohíbe borrado físico administrativo para evitar cascadas sobre cotizaciones, pagos y reembolsos.
- El ADMIN puede establecer cualquier estado canónico aceptado. `CANCELLED` es baja lógica; otros estados conservan sus valores DB y el frontend traduce sus etiquetas.
