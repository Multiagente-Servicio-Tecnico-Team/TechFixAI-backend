---
description: "Tareas de implementación para gestión administrativa de tickets"
---

# Tasks: Gestión administrativa de tickets

**Input**: Documentos de diseño en `specs/004-gestion-admin-tickets/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/admin-tickets.openapi.yaml`, `quickstart.md`

**Testing**: Se incluyen tareas de prueba por los escenarios de aceptación y la constitución del backend. Las pruebas PostgreSQL deben usar una BD desechable explícitamente indicada; nunca cargar `.env` ni usar `DATABASE_URL` como fallback.

**Organization**: Tareas agrupadas por las cuatro historias de usuario de `spec.md`.

## Format

- Cada tarea tiene checkbox, ID secuencial, `[P]` solo si puede ejecutarse en paralelo, etiqueta de historia para tareas de historia y archivos concretos.
- `[US1]` consulta del tablero; `[US2]` alta manual y cotización; `[US3]` detalle/actualización/cancelación; `[US4]` trazabilidad y exportación.

## Phase 1: Setup

**Purpose**: Preparar transporte HTTP para conectar el frontend sin afectar la autorización.

- [X] T001 Permitir `PATCH` desde los orígenes frontend configurados y añadir `Cache-Control: no-store` a las rutas administrativas de tickets en `app/infrastructure/chat_app.py`

---

## Phase 2: Foundational

**Purpose**: Prerrequisitos compartidos que deben estar listos antes de completar cualquiera de las historias.

- [X] T002 [P] Crear la migración aditiva `sql/migrations/004_admin_ticket_management.sql` con `origin`, snapshot de contacto, adelanto/método, `ticket_audit_events` y `customer_id` nullable; mantener `origin=NULL` solo en filas históricas y no borrar/recrear datos
- [X] T003 [P] Definir valores canónicos de origen, tipo de solicitud, estado y método de adelanto con validación de monto en `app/domain/ticket_management.py` usando `Decimal`
- [X] T004 Definir el puerto de persistencia y los modelos de lectura/escritura de tickets administrativos en `app/application/ports.py` y `app/domain/ticket_management.py` (depende de T002 y T003)
- [X] T005 Implementar la base del adaptador PostgreSQL administrativo, incluyendo proyección por origen y `LEFT JOIN` a `users`, en `app/adapters/persistence/admin_tickets.py` (depende de T002 y T004)
- [X] T006 Componer el adaptador y los casos de uso administrativos junto a `require_admin` en `app/infrastructure/chat_app.py` (depende de T001, T004 y T005)

**Checkpoint**: Migración diseñada, valores/puertos definidos, router compuesto y entorno listo para desarrollar historias.

---

## Phase 3: User Story 1 - Consultar y filtrar tickets del taller (Priority: P1) 🎯 MVP

**Goal**: El ADMIN lista y busca tickets con paginación estable, filtros combinables, contacto y tipo/estado/origen canónicos.

**Independent Test**: Con cookie ADMIN, recorrer tickets de distintos clientes y orígenes; verificar que búsqueda/filtros combinados devuelven el conjunto exacto, `total` es el total filtrado y la paginación no duplica ni omite filas.

### Tests for User Story 1

- [X] T007 [P] [US1] Definir pruebas de contrato para filtros, paginación y respuesta `items/total/limit/offset` en `tests/contract/test_admin_ticket_list_contract.py`
- [ ] T008 [P] [US1] Añadir pruebas de consulta para búsqueda por código, contacto, teléfono, equipo y detalle, filtros y orden determinista en `tests/integration/test_admin_ticket_list_api.py`

### Implementation for User Story 1

- [X] T009 [US1] Implementar búsqueda por código, nombre, teléfono, correo, título y descripción, filtros por `status`, `request_type`, `origin`, `total` y orden estable en `app/adapters/persistence/admin_tickets.py`
- [X] T010 [US1] Implementar caso de uso y respuesta paginada con `limit` por defecto 50 y máximo 200 en `app/application/admin_tickets.py` y `app/adapters/api/admin_tickets.py`
- [X] T011 [US1] Mantener los filtros existentes y añadir `origin`/`total` al contrato de `GET /api/admin/tickets` según `specs/004-gestion-admin-tickets/contracts/admin-tickets.openapi.yaml`

**Checkpoint**: El tablero puede obtener el conjunto filtrado completo y paginarlo de manera repetible.

---

## Phase 4: User Story 2 - Registrar ticket manual y cotización posterior (Priority: P1)

**Goal**: El ADMIN crea tickets `MANUAL` sin cuenta, con los campos del formulario y adelanto opcional; después puede guardar una cotización pendiente ligada al ticket.

**Independent Test**: Crear ticket con nombre/teléfono sin cuenta, correo opcional, título, detalle y un tipo válido; verificar el estado inicial y el origen. Crear luego una cotización elegible y comprobar total/relación, sin insertar pago ni reemplazar adelanto.

### Tests for User Story 2

- [X] T012 [P] [US2] Añadir contrato para alta manual, valores requeridos, tipos canónicos y errores de validación en `tests/contract/test_admin_ticket_create_contract.py`
- [ ] T013 [P] [US2] Añadir integración para ticket sin cuenta y límites de contacto en `tests/integration/test_admin_ticket_create_api.py`
- [X] T014 [P] [US2] Añadir pruebas de dominio para adelanto positivo, método requerido y parseo exacto `Decimal` en `tests/unit/domain/test_ticket_management.py`
- [ ] T015 [P] [US2] Añadir contrato y pruebas unitarias para crear quote `PENDING`, vincular ticket y no crear `payments` en `tests/contract/test_admin_ticket_quote_contract.py` y `tests/unit/application/test_admin_ticket_quotes.py`

### Implementation for User Story 2

- [X] T016 [US2] Ampliar DTO de alta con contacto, `title`, `failure_description`, `request_type`, adelanto y método; exigir `contact_name` de 3–200 caracteres, `contact_phone` de 9–20, email opcional válido hasta 255, título de 2–200 y detalle de 5–10000 en `app/adapters/api/admin_tickets.py`
- [X] T017 [US2] Implementar alta transaccional `MANUAL` con `customer_id=NULL`, `status=NEW`, actor ADMIN de sesión, snapshot de contacto y evento `CREATED` en `app/application/admin_tickets.py` y `app/adapters/persistence/admin_tickets.py`
- [X] T018 [US2] Implementar `POST /api/admin/tickets` con `201`, validación de los cinco `request_type` y errores 401/403/422/503 según el contrato en `app/adapters/api/admin_tickets.py`
- [X] T019 [US2] Implementar creación posterior de quote `PENDING` ligada a ticket elegible; calcular total desde mano de obra configurada e inventario vigente con `Decimal`, escribir `quote_details` y no crear pago en `app/application/admin_tickets.py` y `app/adapters/persistence/admin_tickets.py`
- [X] T020 [US2] Añadir `POST /api/admin/tickets/{ticket_id}/quotes`, validar correspondencia `quote_type`/`request_type` y devolver importes como cadenas según el contrato en `app/adapters/api/admin_tickets.py`

**Checkpoint**: El formulario manual puede persistir un ticket sin usuario y añadirle después una cotización que no confunde el adelanto con el total.

---

## Phase 5: User Story 3 - Revisar detalle y actualizar el estado (Priority: P1)

**Goal**: El ADMIN consulta la información completa, cambia campos permitidos o cualquiera de los estados canónicos y cancela sin borrar evidencia.

**Independent Test**: Consultar un ticket manual y uno en línea; actualizar título/detalle/estado; volver a consultarlos y verificar persistencia, autor/fecha de evento y referencias intactas al cancelar.

### Tests for User Story 3

- [ ] T021 [P] [US3] Añadir contrato de detalle, actualización parcial, valores canónicos y rechazo de estado desconocido en `tests/contract/test_admin_ticket_detail_contract.py`
- [ ] T022 [P] [US3] Añadir integración para detalle manual/en línea, actualización permitida, validación e integridad tras cancelación en `tests/integration/test_admin_ticket_update_api.py`

### Implementation for User Story 3

- [X] T023 [US3] Implementar detalle con contacto según origen, quote/pago disponible y fechas en `app/adapters/persistence/admin_tickets.py` y `app/application/admin_tickets.py`
- [X] T024 [US3] Implementar `GET` detalle y `PATCH` para editar título, detalle, tipo, estado, contacto y adelanto; registrar cada cambio con actor ADMIN en una transacción en `app/adapters/api/admin_tickets.py`, `app/application/admin_tickets.py` y `app/adapters/persistence/admin_tickets.py`
- [X] T025 [US3] Deshabilitar el borrado físico: responder `409` documentado en `DELETE /api/admin/tickets/{ticket_id}` y asegurar que la baja se realiza con `status=CANCELLED` sin ejecutar `delete_admin_ticket` en `app/adapters/api/admin_tickets.py` y `app/adapters/persistence/admin_tickets.py`

**Checkpoint**: El ADMIN puede revisar/actualizar/cancelar tickets sin borrar cotizaciones, pagos ni reembolsos asociados.

---

## Phase 6: User Story 4 - Mantener trazabilidad y exportar resultados (Priority: P2)

**Goal**: Cada cambio tiene actor/fecha y detalle administrativo; el portal sigue mostrando solo tickets vinculados al usuario autenticado y la lista completa es exportable.

**Independent Test**: Crear/editar/cancelar ticket y cotización; confirmar eventos atribuibles al actor. Recorrer el resultado filtrado en páginas y comparar el conjunto total sin duplicados. Verificar que un ticket manual sin usuario no aparece en `/api/customer/tickets`.

### Tests for User Story 4

- [ ] T026 [P] [US4] Añadir prueba PostgreSQL aislada para migración, origen histórico NULL, auditoría, restricciones y ausencia de borrado en cascada en `tests/integration/test_admin_ticket_migration_postgres.py`
- [ ] T027 [P] [US4] Añadir prueba de auditoría por actor/evento y aislamiento del portal cliente en `tests/integration/test_admin_ticket_audit_api.py`

### Implementation for User Story 4

- [X] T028 [US4] Registrar origen `ONLINE` y evento inicial derivando `customer_id`/actor de la sesión en la creación de tickets del chat en `app/database/repository.py` y `app/adapters/persistence/tickets.py`
- [X] T029 [US4] Exponer cronología de auditoría con actor, evento y fecha en el detalle admin, sin guardar ni devolver cookies o secretos en `app/adapters/persistence/admin_tickets.py` y `app/adapters/api/admin_tickets.py`
- [X] T030 [US4] Ajustar listado portal para que solo seleccione tickets con `customer_id` del usuario autenticado y nunca filtre manuales sin cuenta en `app/adapters/persistence/tickets.py`

**Checkpoint**: ADMIN puede atribuir cambios y exportar el resultado paginado; los usuarios solo ven sus tickets en línea asociados.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Alinear documentos, validar los contratos y completar la revisión de regresiones del backend.

- [X] T031 [P] Actualizar guía operativa con los pasos de migración de prueba y contrato final en `docs/23-gestion-admin-tickets.md` y `specs/004-gestion-admin-tickets/quickstart.md`
- [X] T032 Revisar que todas las rutas admin usen `require_admin`, respuestas incluyan `Cache-Control: no-store`, PATCH funcione por CORS y los errores respeten el contrato en `app/adapters/api/admin_tickets.py` y `app/infrastructure/chat_app.py`
- [ ] T033 Validar migración solo en BD PostgreSQL desechable, ejecutar pruebas afectadas y compilar `app/`; registrar el destino/migración sin credenciales en `docs/23-gestion-admin-tickets.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Prepara PATCH/CORS y no-store; debe completarse antes de integrar el router con el frontend.
- **Foundational (Phase 2)**: Depende de Setup; migración, dominio, puerto, persistencia y composición bloquean las historias.
- **User Stories**: Dependen de Foundational. US1 habilita las vistas del tablero; US2 añade el alta/cotización; US3 añade detalle/edición/cancelación; US4 completa trazabilidad y compatibilidad con el portal.
- **Polish (Phase 7)**: Depende de US1–US4 y de aplicar la migración únicamente a una BD de prueba autorizada.

### User Story Dependencies

- **US1 (P1)**: Puede comenzar tras Phase 2; no depende funcionalmente de US2–US4.
- **US2 (P1)**: Puede comenzar tras Phase 2; el alta/cotización reutiliza la persistencia base de US1 si ya está integrada. Los archivos compartidos del router/repositorio aconsejan integrar secuencialmente.
- **US3 (P1)**: Puede comenzar tras Phase 2; comparte ticket DTO y persistencia con US1/US2, por lo que conviene integrar después de US2.
- **US4 (P2)**: Se valida tras US2/US3 para verificar eventos de todo el ciclo y aislamiento del portal; migración/auditoría son prerrequisitos fundacionales.

### Parallel Opportunities

- **Phase 2**: T002 (SQL) y T003 (tipos/validadores) trabajan archivos distintos; T004 espera ambos.
- **US1**: T007 y T008 son contratos/pruebas en módulos diferentes y pueden prepararse en paralelo; implementación espera ambos.
- **US2**: T012, T013, T014 y T015 se pueden preparar en paralelo porque usan archivos de prueba distintos; T016–T020 se integran según dependencia en los DTO/casos de uso.
- **US3**: T021 y T022 pueden prepararse en paralelo; implementación comparte router/adaptador y se ejecuta secuencialmente.
- **US4**: T026 y T027 son pruebas independientes; el cambio de creación online T028 debe coordinarse con `repository.py` y el adaptador de portal.

## Parallel Example: User Story 1

```text
Task: "Contrato de filtros/paginación en tests/contract/test_admin_ticket_list_contract.py"
Task: "Integración de búsqueda/orden en tests/integration/test_admin_ticket_list_api.py"
```

## Implementation Strategy

### MVP First

1. Completar Setup y Foundational, incluida la migración solo en una BD desechable.
2. Implementar US1: listado paginado, filtros, búsqueda y total; esto entrega el tablero consultable.
3. Validar US1 de forma independiente antes de pasar a alta manual.

### Incremental Delivery

1. US1 → tablero con datos reales.
2. US2 → creación manual sin cuenta y cotización posterior asociada.
3. US3 → detalle, actualización de estado y cancelación segura.
4. US4 → auditoría completa y aislamiento del portal cliente.
5. Polish → migración y regresión verificada con resultados documentados.

## Notes

- Cada tarea es concreta, tiene ruta de archivo y sigue el formato checkbox/ID; `[P]` solo indica trabajo en archivos independientes.
- Las tareas de prueba están antes de la implementación de su historia.
- No ejecutar SQL de recreación ni aplicar `004_admin_ticket_management.sql` a una BD compartida/producción.
- La generación de este archivo no modifica código ni ejecuta pruebas.




