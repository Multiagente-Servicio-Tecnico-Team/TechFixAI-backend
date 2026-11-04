# Tasks: Gestión de clientes comerciales

**Input**: Design documents from `specs/007-gestion-clientes-comerciales/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/customer-commerce.openapi.yaml), [quickstart.md](quickstart.md)

**Tests**: Incluidos porque el spec define escenarios independientes y la constitución exige contratos de negocio comparables para los tres patrones. Estas tareas describen pruebas futuras; no se ejecutan en esta fase.

**Organization**: Tareas agrupadas por historias de usuario. La limpieza de datos autorizada está separada de la migración estructural y exige preflight.

## Formato

Cada tarea sigue `- [ ] T### [P?] [US#?] Descripción con archivo`. `[P]` indica que puede avanzar en paralelo sin editar los mismos archivos ni depender de una tarea incompleta.

## Phase 1: Setup

**Purpose**: Preparar el proceso reproducible de migraciones y el entorno de validación aislado.

- [X] T001 Documentar cómo tomar baseline, inspeccionar migraciones realmente aplicadas y no inferir aplicación desde archivos en `sql/migrations/README.md`.
- [X] T002 Documentar requisitos de respaldo, identificación de destino y protección de datos para cambios de esquema en `docs/migrations/customer-commerce.md`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Reconciliar el esquema vivo y establecer las estructuras compartidas que bloquean las historias.

- [X] T003 [P] Implementar reconciliación/registro versionado de migraciones sin marcar versiones no verificadas como aplicadas en `app/database/migrations.py`.
- [X] T004 Crear la migración aditiva `sql/migrations/006_customer_commerce_expand.sql` con tabla `customers`, campos `commercial_customer_id` nullable en `tickets`/`payments`, `customer_id` nullable en `quotes`, campos de autoría y `quotes.ticket_id` nullable; conservar las columnas `customer_id` legacy que apuntan a users hasta el corte posterior.
- [X] T005 [P] Definir tipos, errores e invariantes compartidos para customer, quote, payment, sales order y reserva en `app/domain/customer_commerce.py`.
- [X] T006 Preparar factories y fixture de PostgreSQL aislado para escenarios de clientes/comercio en `tests/fixtures/customer_commerce.py`.

**Checkpoint**: Estado de migraciones reconciliado; esquema expandido y modelos comunes listos sin corte de compatibilidad.

---

## Phase 3: User Story 1 — Clientes con o sin cuenta del portal (P1) 🎯 MVP

**Goal**: Administrar perfiles comerciales manuales y perfiles vinculados a cuentas sin crear credenciales ficticias.

**Independent Test**: Crear un cliente manual sin fila nueva en `users`; vincular una cuenta CUSTOMER con verificación explícita; demostrar que un segundo vínculo de esa cuenta falla y que coincidencias de teléfono/correo no fusionan perfiles.

### Tests for User Story 1

- [X] T007 [P] [US1] Añadir pruebas unitarias de restricciones del perfil (nombre/teléfono no vacíos, email opcional, `origin` MANUAL/PORTAL, `user_id` nullable único, sin unicidad global por email/teléfono) en `tests/unit/domain/test_customer_profiles.py`.
- [X] T008 [P] [US1] Añadir pruebas de contrato para CRUD ADMIN, vínculo verificado y rechazo de acceso sin ADMIN en `tests/contract/test_customer_api_contract.py`.
- [X] T009 [P] [US1] Añadir pruebas de que la sesión CUSTOMER resuelve su perfil y que el payload no puede sustituir su identidad en `tests/unit/application/test_customer_session_resolution.py`.

### Implementation for User Story 1

- [X] T010 [US1] Implementar entidad y validaciones de `CustomerProfile` con `user_id` opcional único, origen limitado a MANUAL/PORTAL y ninguna credencial en `app/domain/customer_profiles.py`.
- [X] T011 [US1] Implementar casos de uso de alta/búsqueda/lectura/actualización y vínculo de cuenta con actor ADMIN en `app/application/customer_profiles.py`.
- [X] T012 [US1] Implementar persistencia PostgreSQL de `customers`, búsqueda sin deduplicación por correo/teléfono y autoría en `app/adapters/persistence/customers.py`.
- [X] T013 [US1] Implementar rutas `/api/admin/customers` y `/api/admin/customers/{customer_id}/link-account` con roles, validaciones y respuestas OpenAPI en `app/adapters/api/customers.py`.
- [X] T014 [US1] Registrar el router de customers y el caso de resolución de identidad sin cambiar la cookie ni `SessionCustomer.id` en `app/main.py` y `app/accounts/session.py`.
- [X] T015 [US1] Verificar compatibilidad del schema de respuesta y documentar error codes para cuenta ya vinculada, customer inexistente y sesión/rol inválido en `specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml`.

---

## Phase 4: User Story 2 — Tickets de servicio con cotización opcional (P1)

**Goal**: Asociar tickets manuales y online a customers; conservar tickets de reparación/soporte/armado y separar actor del cliente.

**Independent Test**: Crear ticket para cliente manual y para cliente del portal; confirmar que el ticket puede tener cero o más cotizaciones de servicio, cada una del mismo customer, y que otra sesión no puede consultarlo.

### Tests for User Story 2

- [X] T016 [P] [US2] Añadir pruebas de contrato para alta ADMIN, alta portal por sesión, listados propios y respuestas con cero/múltiples quotes en `tests/contract/test_customer_service_ticket_contract.py`.
- [X] T017 [P] [US2] Añadir pruebas de persistencia y auditoría que exijan `customer_id`, snapshots de contacto y actor ADMIN separado en `tests/integration/test_customer_service_ticket_repository.py`.

### Implementation for User Story 2

- [X] T018 [US2] Actualizar entidad/casos de uso de tickets para recibir customer resuelto y mantener actor/auditoría separados en `app/domain/tickets.py` y `app/application/tickets.py`.
- [X] T019 [US2] Adaptar persistencia administrativa y portal para leer/escribir `customers.id`, conservar snapshots y filtrar por sesión resuelta en `app/adapters/persistence/admin_tickets.py` y `app/adapters/persistence/tickets.py`.
- [X] T020 [US2] Adaptar rutas de gestión ADMIN para seleccionar/crear customer comercial sin generar cuenta y mantener enums del backend en `app/adapters/api/admin_tickets.py`.
- [X] T021 [US2] Adaptar rutas de tickets portal para resolver customer desde cookie firmada y rechazar `customer_id` libre en `app/adapters/api/chat.py`.
- [X] T022 [US2] Ajustar contrato de ticket y cotización de servicio a `customer-commerce.openapi.yaml`, incluyendo `ticket.customer_id = quote.customer_id`.

---

## Phase 5: User Story 3 — Cotizaciones de venta directas y reservas (P1)

**Goal**: Crear ofertas de productos sin ticket de taller y reservar stock al aceptarlas, sin sobreventa.

**Independent Test**: Crear venta directa con `ticket_id = null`; aceptar cotización con stock suficiente para crear reserva completa; probar simultaneidad/stock insuficiente y liberar al rechazar, cancelar o vencer.

### Tests for User Story 3

- [ ] T023 [P] [US3] Completar la cobertura unitaria existente para el ciclo de reserva, idempotencia, expiración y cálculo de disponible (`current_stock - reservas activas`) en `tests/unit/application/test_sales_quote_reservations.py`.
- [ ] T024 [P] [US3] Completar los contratos existentes para stock insuficiente y ausencia de reserva parcial; ya están cubiertos alta ADMIN, ownership portal y paso de clave idempotente en `tests/contract/test_sales_quote_contract.py`.
- [ ] T025 [P] [US3] Añadir prueba de concurrencia que impida reservar más unidades que el stock disponible en `tests/integration/test_inventory_reservation_concurrency.py`.

### Implementation for User Story 3

- [X] T026 [US3] Implementar migración de reservas/líneas y `sales_orders`/`sales_order_items` con estados, vencimiento, actor, cantidad positiva, FK restrictivas e índices idempotentes en `sql/migrations/007_inventory_reservations.sql`; crear pedido solo cuando se confirme pago.
- [X] T027 [US3] Extender `inventory_movements` en `sql/migrations/007_inventory_reservations.sql`: `sales_order_item_id` nullable, `purchase_receipt_item_id` nullable, check XOR de origen y check de `movement_type`, preservando movimientos de recepción existentes.
- [X] T028 [US3] Implementar casos de uso de cotización directa y transiciones PENDING/ACCEPTED/REJECTED/CANCELLED/EXPIRED, con vencimiento obligatorio para reservas, en `app/application/sales_quotes.py`.
- [X] T029 [US3] Implementar reserva completa o rollback completo en una transacción, con locks de repuestos en orden estable, clave idempotente y cálculo contra reservas activas en `app/adapters/persistence/sales_quotes.py`.
- [X] T030 [US3] Implementar rutas de creación/listado/detalle ADMIN, aceptación manual ADMIN y lectura/aceptación de quote propio por sesión en `app/adapters/api/sales_quotes.py`.
- [X] T031 [US3] Evitar que edición de inventario reduzca `current_stock` por debajo de reservas activas o borre repuestos reservados en `app/adapters/persistence/inventory.py`.
- [ ] T032 [US3] Completar el flujo de venta directa en el patrón Orquestador y devolver su `quote_id`; Jerárquico y Descentralizado ya crean/aceptan cotizaciones directas. Mantener la política de reservas compartida, no crear ticket `SALE` ni permitir que el LLM confirme pago/stock en `app/agents/orquestador/agentes/ventas.py`, `app/agents/orquestador/graph/` y `app/adapters/patterns/orchestrator.py`.
- [X] T033 [US3] Actualizar contrato API de ventas con `ticket_id` nulo, `expires_at` requerido, estado de reserva y conflicto sin reserva parcial en `specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml`.

---

## Phase 6: User Story 4 — Pagos, pedidos y trazabilidad financiera (P1)

**Goal**: Confirmar pago solo con ADMIN y evidencia, crear un pedido idempotente y adaptar dependencias que hoy exigen ticket.

**Independent Test**: Quote aceptada permanece con pago pendiente; ADMIN confirma una vez; una venta/pedido y salida de stock se registran una sola vez; portal consulta solo sus pagos/ventas.

### Tests for User Story 4

- [ ] T034 [P] [US4] Añadir contratos de transición de pago, rechazo para CUSTOMER, actor/fecha persistidos y repetición idempotente; `tests/contract/test_sales_quote_contract.py` hoy solo comprueba ADMIN y que se propaga la clave idempotente.
- [ ] T035 [P] [US4] Añadir integración que compruebe consumo de reserva, stock decrementado y movimiento SALE único por línea en `tests/integration/test_sales_order_inventory.py`.
- [ ] T036 [P] [US4] Añadir pruebas de reembolso/logística/garantía para venta directa sin ticket y conservar flujos de servicio con ticket en `tests/integration/test_ticketless_sale_dependents.py`.

### Implementation for User Story 4

- [X] T037 [US4] Implementar estados y validaciones compartidas de cotización, pago, pedido y reserva en `app/domain/customer_commerce.py` y `app/application/sales_quotes.py`.
- [X] T038 [US4] Implementar confirmación ADMIN atómica/idempotente: consume reserva, actualiza stock y crea pedido/pago/movimientos/auditoría en `app/adapters/persistence/sales_quotes.py`.
- [X] T039 [US4] Implementar rutas ADMIN/cliente para confirmación de pago y consulta de cotizaciones, pedidos y pagos, con ownership resuelto por sesión, en `app/adapters/api/sales_quotes.py`.
- [X] T040 [US4] Adaptar reembolsos a customer/payment/quote/order y permitir `ticket_id` nulo solo en ventas directas, manteniendo solicitud pendiente de revisión en `app/application/refunds.py` y `app/database/repository.py`.
- [X] T041 [US4] Adaptar logística para que reparaciones sigan ligadas a ticket y ventas ligadas a sales order sin duplicar preferencias en `app/application/logistics.py` y `app/database/repository.py`.
- [X] T042 [US4] Adaptar garantías para conservar garantías de servicio/taller por ticket y admitir garantías de venta por sales order/customer en `app/application/warranties.py` y `app/database/repository.py`.
- [X] T043 [US4] Actualizar OpenAPI para pagos, ventas, confirmación ADMIN, ownership y estados/respuestas de error en `specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml`.

---

## Phase 7: User Story 5 — Migración conservadora y limpieza autorizada (P1)

**Goal**: Migrar registros previos sin perder datos ni ownership, y retirar únicamente el fixture SALE aprobado con una operación aparte y verificable.

**Independent Test**: Ejecutar en copia restaurada; preservar el 100% de registros ajenos al fixture; migrar customer/actor/quotes/payments y snapshots; preflight de cleanup aborta si IDs/counts/dependencias difieren; ejecución de prueba informa cada fila borrada.

### Tests for User Story 5

- [ ] T044 [P] [US5] Añadir pruebas de backfill uno-a-uno desde users y tickets manuales, sin fusión por email/teléfono y con conservación de IDs/importes/estados/fechas en `tests/integration/test_customer_commerce_migration.py`.
- [ ] T045 [P] [US5] Ampliar las pruebas existentes del cleanup para cubrir dependencias desconocidas, destino no autorizado y rollback sin borrado parcial; hoy solo se valida el manifiesto y el rechazo de un conjunto de IDs distinto en `tests/unit/test_sale_fixture_cleanup.py`.
- [ ] T046 [P] [US5] Añadir prueba de migración que valide FKs vivas, conteos antes/después e invariantes de ticket/quote/payment/customer en `tests/integration/test_customer_commerce_schema_migration.py`.

### Implementation for User Story 5

- [X] T047 [US5] Implementar backfill repetible desde users a customers con tabla/mapeo de auditoría y reporte de inconsistencias en `sql/migrations/008_customer_commerce_backfill.sql`.
- [X] T048 [US5] Implementar backfill separado de tickets legados sin user usando un customer individual por registro y preservando snapshots/actor en `sql/migrations/008_customer_commerce_backfill.sql`.
- [X] T049 [US5] Añadir verificación pre/post de recuentos, huérfanos, quote totals, pagos y ownership, y aplicar constraints finales solo si pasa en `sql/migrations/009_customer_commerce_constraints.sql`.
- [X] T050 [US5] Crear preflight de operación de limpieza que compruebe entorno de prueba, ocho IDs exactos aprobados, todos sus hijos/FKs y conteos antes de habilitar mutación en `sql/operations/cleanup_sale_test_fixture.py`.
- [X] T051 [US5] Implementar cleanup separado, transaccional y con abortos por discrepancia para solo el manifiesto verificado; nunca borrar con filtro genérico por tipo en `sql/operations/cleanup_sale_test_fixture.py`.
- [X] T052 [US5] Guardar reporte de filas por tabla, respaldo requerido, hora, destino no sensible y resultado de cleanup en `docs/migrations/007-sale-test-fixture-cleanup.md`.
- [X] T053 [US5] Mantener compatibilidad de rutas/lecturas legacy y documentar corte posterior coordinado con el frontend antes de eliminar columnas/FK antiguas en `app/adapters/api/admin_tickets.py` y `docs/migrations/customer-commerce.md`.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Verificar consistencia compartida, seguridad y guía operativa; no borrar ni migrar datos aquí.

- [ ] T054 [P] Añadir prueba común para ownership, quote/pago y políticas de stock aplicada a Jerárquico, Orquestador y Descentralizado según capacidades declaradas en `tests/contract/patterns/test_customer_commerce_patterns.py`.
- [X] T055 [P] Actualizar documentación de API/compatibilidad, decisiones de estados y separación de frontend en `specs/007-gestion-clientes-comerciales/quickstart.md` y `README.md`.
- [ ] T056 Revisar y ejecutar el quickstart completo solo contra PostgreSQL aislado; registrar resultado y conteos de migración en `docs/migrations/customer-commerce.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no depende de historias; establece procedimiento de baseline y respaldo.
- **Foundational (Phase 2)**: depende de Setup y bloquea las historias; no elimina relaciones legacy.
- **US1 (Phase 3)**: depende de Foundational; MVP inicial de perfil comercial y resolución de sesión.
- **US2 (Phase 4)**: depende de US1 para asociar tickets a customers.
- **US3 (Phase 5)**: depende de US1; cotización directa puede avanzar en paralelo con partes independientes de US2, pero su aceptación requiere reserva.
- **US4 (Phase 6)**: depende de US3 para quote aceptada/reserva y consume sus datos; debe completar side effects de stock/venta de forma atómica.
- **US5 (Phase 7)**: backfill depende de esquema Foundational; cutover y constraints dependen de US1–US4. La limpieza autorizada es separada y puede prepararse en paralelo, pero su ejecución requiere backup, manifiesto exacto y preflight aprobado.
- **Polish (Phase 8)**: depende de las historias seleccionadas y de la validación aislada; no ejecuta limpieza sobre datos persistentes.

### User Story Dependencies

- **US1**: primera entrega funcional; habilita identidad comercial y clientes manuales sin crear cuentas.
- **US2**: requiere US1; tickets solo modelan servicio y heredan el customer resuelto.
- **US3**: requiere US1; venta directa sin ticket y reserva de inventario.
- **US4**: requiere US3; pagos confirmados convierten reserva en pedido/venta y adaptan dependencias.
- **US5**: expansión del esquema comienza en Foundational; backfill/constraints requieren contratos nuevos; limpieza solo después de fijar el destino y los IDs reales.

### Parallel Opportunities

- T003 y T005 pueden desarrollarse en paralelo; T004 requiere baseline acordado en T001.
- En US1, T007–T009 son pruebas independientes en archivos distintos; T011 y T012 pueden avanzar por separado una vez fijado T010.
- En US2, T016 y T017 pueden avanzar en paralelo; API y repositorios pueden implementarse en paralelo si el dominio/contrato están congelados.
- En US3, pruebas unitarias, contrato y concurrencia (T023–T025) pueden prepararse en paralelo; persistencia e integración de chat requieren esquema y contratos acordados.
- En US4, T034–T036 son pruebas separables; refund, logística y warranty pueden implementarse en paralelo tras definir las nuevas relaciones a order/payment.
- En US5, T044–T046 pueden escribirse en paralelo; preflight y reporte (T050/T052) pueden prepararse en paralelo, pero la ejecución T051 no inicia hasta pasar el preflight.

## Parallel Example: User Story 1

```text
Task: T007 pruebas unitarias de perfil en tests/unit/domain/test_customer_profiles.py
Task: T008 pruebas de contrato ADMIN y vínculo en tests/contract/test_customer_api_contract.py
Task: T009 pruebas de resolución de sesión en tests/unit/application/test_customer_session_resolution.py
```

## Parallel Example: User Story 3

```text
Task: T023 pruebas de estado/reserva en tests/unit/application/test_sales_quote_reservations.py
Task: T024 contrato HTTP en tests/contract/test_sales_quote_contract.py
Task: T025 carrera de stock en tests/integration/test_inventory_reservation_concurrency.py
```

## Implementation Strategy

### MVP First (US1)

1. Completar Setup y Foundational sobre una base aislada.
2. Completar US1: crear clientes manuales, buscar clientes y vincular una cuenta autenticada con verificación.
3. Validar US1 de forma independiente antes de adaptar tickets o comercio.

### Incremental Delivery

1. US1 crea el registro comercial y la resolución user→customer.
2. US2 mueve tickets manuales/online al nuevo customer manteniendo compatibilidad.
3. US3 separa cotización de venta y reserva stock al aceptar.
4. US4 agrega pago verificado, pedido y operaciones dependientes.
5. US5 migra/corta datos, limpia solo el fixture autorizado y documenta resultado.
6. Ejecutar Polish contra entorno de prueba; coordinar con un Spec-Kit separado los cambios frontend antes de retirar contratos legacy.

## Notes

- `[P]` significa tareas paralelizables; `[US#]` enlaza tarea con historia del spec.
- No aplicar una migración solo porque el archivo exista; consultar/reconciliar el estado real del esquema y usar respaldo.
- No ejecutar cleanup en bases de despliegue ni seleccionar todos los tickets por `SALE`; los ocho IDs deben verificarse en la base de prueba autorizada antes de cualquier borrado.
- No marcar pagos como completados por aceptación de quote ni por texto del LLM.
- Las tareas describen la implementación futura; este comando solo genera el plan de tareas.
