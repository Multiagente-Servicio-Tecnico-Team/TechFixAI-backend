# Research: Gestión administrativa de tickets

## Decisiones

### 1. Reusar `request_type` para el selector “Categoría”

- **Decisión**: No crear una segunda clasificación. El selector muestra los valores canónicos `REPAIR`, `SALE`, `PC_BUILD`, `SUPPORT` y `WARRANTY_CLAIM` con etiquetas en español y envía esos códigos.
- **Razón**: `request_type_enum` ya define los cinco tipos; duplicarlos como Reparación/Venta/Soporte dejaría ambiguos Armado de PC y Garantía.
- **Alternativas**: Mantener solo las tres opciones actuales excluiría tipos ya admitidos; añadir una categoría paralela duplicaría la semántica.

### 2. Distinguir origen de ticket y cuenta de cliente

- **Decisión**: Los tickets nuevos registran `origin` como `MANUAL` o `ONLINE`. En `MANUAL`, nombre y teléfono se capturan en el ticket, correo es opcional y `customer_id` puede ser nulo. En `ONLINE`, `customer_id` se obtiene de la sesión autenticada y es obligatorio.
- **Razón**: `users` exige correo, teléfono y hash de contraseña, por lo que no representa un contacto presencial sin cuenta. La identidad de los tickets online no debe aceptarse del body.
- **Alternativas**: Crear usuarios ficticios para mostrador introduce credenciales falsas; copiar todos los datos a nuevos clientes de `users` exige datos que el formulario no pide.
- **Histórico**: El esquema actual no conserva el origen. Filas existentes reciben `origin = NULL` (origen histórico desconocido) en vez de inventar si fueron manuales o en línea. Las nuevas escrituras sí exigen uno de los dos valores.

### 3. Guardar contacto y adelanto en el ticket

- **Decisión**: Añadir snapshot de nombre, teléfono y correo; importe de adelanto y método capturados al ingreso manual. Aceptar los métodos actuales Yape/Plin, efectivo y tarjeta en atributos del ticket, sin alterar el enum de `payments` ni crear una transacción de pago por inferencia.
- **Razón**: El formulario llama al importe “Monto cobrado / Adelanto” y esos datos deben persistir incluso sin cuenta. `payments.customer_id` es obligatorio y representa una transacción del sistema con estados; el formulario manual no prueba ni procesa una transacción electrónica.
- **Alternativas**: Reutilizar `payments` sin `customer_id` o expandir su método mezclaría el recibo manual del ticket con el flujo transaccional online.
- **Validación**: Importe ausente implica método ausente; un adelanto positivo requiere método. Guardar con `NUMERIC`/`Decimal`, no `float`.

### 4. Crear la cotización después y vincularla al ticket

- **Decisión**: Mantener `quotes.ticket_id` y `quotes.total_amount` como registro posterior del costo total; no usar el adelanto como costo total. El plan incluye una operación administrativa para guardar una cotización pendiente ligada al ticket manual y reutilizar cálculo/validación de importes e inventario cuando aplique.
- **Razón**: El esquema ya tiene la relación y el importe total. Los helpers actuales generan cotizaciones aceptadas/pagos en flujos autenticados, así que el caso manual necesita una ruta/caso de uso que no dependa de un `customer_id` inexistente ni cree un pago automáticamente.
- **Alternativas**: Crear cotización durante la recepción contradice el flujo mostrado (primero se registra y diagnostica el equipo). Guardar el total en `tickets` duplicaría la fuente del total.

### 5. Cancelar en vez de borrar físicamente

- **Decisión**: Reemplazar el borrado físico administrativo por cambio a `CANCELLED` y evento auditable; retirar o deshabilitar `DELETE`.
- **Razón**: En el SQL, `quotes`, `payments` y `refunds` usan referencias con `ON DELETE CASCADE` desde tickets. Una eliminación podría borrar evidencia financiera.
- **Alternativas**: Permitir DELETE solo cuando no haya dependencias deja una operación destructiva y estados inconsistentes entre pantallas; la cancelación conserva historia.

### 6. Registrar eventos de auditoría

- **Decisión**: Añadir historial append-only para creación, edición, cambio de estado, cancelación y creación de cotización, con actor derivado de sesión y fecha. No completar retroactivamente autores que no están en datos existentes.
- **Razón**: `tickets` solo tiene `created_at`/`updated_at`; la especificación exige identificar quién hizo cada cambio.
- **Alternativas**: Sobrescribir solo `updated_at` no deja trazabilidad; guardar payloads completos copiaría PII innecesaria.

### 7. Ampliar filtros y paginación administrativa

- **Decisión**: Mantener búsqueda, estado, tipo y `limit/offset`; añadir origen y teléfono al filtro/búsqueda, total filtrado y orden determinista por fecha/ID.
- **Razón**: El tablero busca por cliente, dispositivo y código, filtra estado/tipo y exporta el conjunto completo. La consulta actual no busca teléfono y no devuelve total.
- **Alternativas**: Descargar una sola página omite tickets en CSV; orden no determinista puede duplicar/omitir resultados al paginar.

## Hallazgos de código que afectan el plan

- `app/adapters/api/admin_tickets.py`: las rutas actuales ya están protegidas por `require_admin`; POST exige `customer_email`; PATCH acepta estados canónicos; DELETE borra físicamente.
- `app/database/repository.py`: `list_admin_tickets()` y `get_admin_ticket()` hacen `JOIN users`, requieren cambiar a unión externa para tickets manuales. `delete_admin_ticket()` ejecuta `DELETE`. `create_intake_ticket()` crea tickets online con cuenta autenticada.
- `app/accounts/session.py`: `SessionGuard.require_admin` valida la cookie y el rol; el actor de auditoría debe venir de `SessionCustomer.id`.
- `contexto/tablas postgres v2.sql` (snapshot vigente desde 2026-11-03): request types cubiertos; `tickets.customer_id` es nullable tras la migración 004; `quotes.ticket_id/total_amount` existen; los pagos conservan su propio cliente y métodos separados del adelanto administrativo.
- `TechFixAI-frontend/src/features/workshop/NewTicket.jsx`: captura contacto, equipo/modelo, detalle, tres categorías y adelanto; sigue usando estado demo local.
- No se encontró Alembic. El proyecto versiona SQL en `sql/migrations/`; la migración nueva será aditiva y se documentará para aplicación explícita en BD de prueba.

## Límites

- La planificación no ejecuta migraciones ni modifica el SQL fuente de esquema.
- La interfaz frontend se implementará en su repositorio en una feature separada.
- Los estados y tipos existentes no se renombrarán en base de datos; el frontend traduce etiquetas y conserva valores canónicos.
