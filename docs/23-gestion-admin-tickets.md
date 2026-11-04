# Gestión administrativa de tickets

La API administrativa de tickets requiere una sesión firmada con rol `ADMIN`. El listado devuelve `items`, `total`, `limit` y `offset`; admite `status`, `request_type`, `origin` y `search`. La creación administrativa registra `origin=MANUAL`, contacto sin cuenta, `status=NEW` y una auditoría atribuida a la sesión. Los tickets online registran `origin=ONLINE` y su cliente desde la sesión autenticada.

## Migración

Antes de iniciar la nueva versión, aplicar `sql/migrations/004_admin_ticket_management.sql` a una base PostgreSQL desechable. Hace nullable `tickets.customer_id`, añade el origen/contacto/adelanto y crea `ticket_audit_events`. Los tickets existentes mantienen `origin=NULL`; no se infiere su canal ni se modifican sus cotizaciones y pagos. No aplicar la migración a producción sin respaldo y revisión propia.

La aplicación no carga `.env` como destino alternativo para pruebas de migración. El test de PostgreSQL de esta feature debe recibir una URL de base de datos desechable explícita en `TICKETS_TEST_DATABASE_URL`.

## Operaciones

- `GET /api/admin/tickets`: filtros, búsqueda y paginación estable.
- `POST /api/admin/tickets`: alta manual con nombre, teléfono, equipo, detalle y tipo. Adelanto opcional, almacenado en el ticket y sin crear un pago.
- `GET/PATCH /api/admin/tickets/{id}`: detalle, auditoría y edición; usar `status=CANCELLED` para dar de baja.
- `DELETE /api/admin/tickets/{id}`: responde `409`; no elimina evidencia contable ni de auditoría.
- `POST /api/admin/tickets/{id}/quotes`: agrega cotización `PENDING` con precios vigentes del inventario y mano de obra configurada. No registra pago.

El frontend debe enviar los valores canónicos del backend. Los tipos de solicitud son `REPAIR`, `SALE`, `PC_BUILD`, `SUPPORT` y `WARRANTY_CLAIM`; el canal MANUAL/ONLINE se asigna desde el servidor.
