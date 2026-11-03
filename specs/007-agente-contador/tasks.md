# Tasks: Asistente contable común

**Sources**: [spec.md](spec.md), [plan.md](plan.md), [checklist](checklists/requirements.md), constitución, specs 001/003/006 y contrato OpenAPI de 003.
**Scope**: tareas futuras; este archivo no implementa código. D1/D2 de 003 y FR-015 de 006 son invariantes.
**Stories**: US1 consulta contable; US2 ingreso y creación manual; US3 reversión.

## Phase 1 — Contrato de vista previa de chat

**Goal**: acordar una salida opcional, estructurada y exclusiva para ADMIN en POST /api/chat antes de implementarla.

- [ ] T001 [US2] Definir en specs/007-agente-contador/plan.md el esquema de vista previa opcional de ChatOut: campos de CreateAccountingEntry de 003, totales PEN, estado de validación y ausencia de correlativo, sin cambiar ChatIn ni añadir una acción de confirmación.
- [ ] T002 [US2] Coordinar la aprobación del esquema de salida con responsables de app/chat/contract.py y del repositorio frontend; registrar la decisión en specs/007-agente-contador/plan.md. BLOQUEADA hasta que esos responsables acuerden nombre, forma y compatibilidad del campo; no depende de una regla contable nueva.
- [ ] T003 [US2] Implementar únicamente el campo de salida opcional aprobado en app/chat/contract.py, manteniendo los campos existentes y sin añadir endpoint o acción contable; verificar serialización y compatibilidad en tests/contract/patterns/test_accounting_assistant_contract.py. Depende de T002.

## Phase 2 — Guía de ingreso manual y validación

**Goal**: recoger solo datos de ADMIN y aplicar las reglas deterministas de 003.

- [ ] T004 [US2] Crear el caso de uso compartido de guía manual en app/application/accounting_assistant.py para fecha, concepto, detalle, category_id y 2–100 líneas con código, denominación, descripción opcional y debe/haber; no leer operaciones comerciales ni inferir valores.
- [ ] T005 [US2] Reutilizar EntryDraft, EntryLine y validate_draft de app/domain/accounting.py desde app/application/accounting_assistant.py: Decimal/PEN, importe positivo en exactamente un lado, precisión de 003 y totales debe/haber iguales; pedir cada dato ausente o inválido.
- [ ] T006 [US2] Aplicar en app/application/accounting_assistant.py la restricción de no inventar cuentas, importes, IGV, costos o fechas y de no derivar líneas de ventas, compras, pagos, cotizaciones, reembolsos o inventario.

## Phase 3 — Vista previa temporal sin escritura

**Goal**: devolver la vista previa y demostrar que no crea asientos.

- [ ] T007 [US2] Componer en app/application/accounting_assistant.py un resultado temporal con los datos manuales y totales validados, sin id de asiento, correlativo, estado DRAFT ni llamada a create_entry.
- [ ] T008 [US2] Exponer ese resultado solo a ADMIN mediante el adaptador de chat en app/adapters/api/chat.py y la salida opcional de app/chat/contract.py; evitar que el checkpoint de app/agents/decentralized/workflow/state.py conserve un borrador contable.
- [ ] T009 [US2] Comprobar en tests/unit/application/test_accounting_assistant.py y tests/contract/patterns/test_accounting_assistant_contract.py que una solicitud de vista previa válida, incompleta o desbalanceada no invoca escritura ni cambia el libro contable.

## Phase 4 — Operaciones existentes de 003

**Goal**: reutilizar consultas, creación por API y reversión sin duplicar rutas ni persistencia.

- [ ] T010 [US1] Conectar consultas de categorías, listado con filtros y detalle al AccountingService existente de app/application/accounting.py; respetar permisos ADMIN de app/accounts/session.py y respuestas del contrato specs/003-asientos-contables/contracts/accounting.openapi.yaml.
- [ ] T011 [US2] Mantener la creación exclusivamente en POST /api/admin/accounting/entries de app/adapters/api/accounting.py: el frontend envía el payload revisado y una Idempotency-Key UUID tras Confirmar; la API revalida sesión ADMIN, categoría, estructura y balance antes de crear CONFIRMED en una operación. No agregar confirmación a POST /api/chat.
- [ ] T012 [US3] Conectar la consulta y solicitud de reversión con motivo al AccountingService existente de app/application/accounting.py y a POST /api/admin/accounting/entries/{entry_id}/reverse; conservar original, actor, historial e idempotencia de 003, sin nueva ruta.

## Phase 5 — Integración por patrón

**Goal**: conectar la capacidad compartida conservando la coordinación propia de cada patrón.

- [ ] T013 [US1] Integrar en app/adapters/patterns/decentralized.py y app/agents/decentralized/workflow/graph.py el acceso ADMIN a consultas y guía contable compartidas, conservando los nueve roles actuales, identificadores, handoffs, ownership, locks y recuperación, sin nodos alias duplicados.
- [ ] T014 [US2] Verificar en app/agents/decentralized/workflow/state.py y app/adapters/patterns/decentralized.py que la vista previa no se almacena como borrador durable ni altera rutas comerciales.
- [ ] T015 [US1] Registrar en specs/007-agente-contador/plan.md la coordinación requerida para equivalencia de contrato, permisos y resultados en app/adapters/patterns/orchestrator.py y app/adapters/patterns/hierarchical.py; BLOQUEADA para integración hasta que los responsables de Orquestador y Jerárquico acuerden su punto de delegación. No modificar su código en este worktree.

## Phase 6 — Contrato para frontend

**Goal**: documentar el flujo de confirmación sin implementar frontend.

- [ ] T016 [US2] Documentar en specs/007-agente-contador/plan.md el campo de vista previa aprobado, botón Confirmar, retención temporal, envío de cookie, payload CreateAccountingEntry e Idempotency-Key al POST existente de 003 y tratamiento de 201/200/401/403/409/422/503; coordinar con el responsable frontend sin modificar ese repositorio. Depende de T002.

## Phase 7 — Pruebas aisladas y de contrato

**Goal**: demostrar acceso, validación, ausencia de escritura y equivalencia sin servicios externos.

- [ ] T017 [US1] Añadir en tests/unit/application/test_accounting_assistant.py y tests/contract/patterns/test_accounting_assistant_contract.py casos ADMIN, rechazo CUSTOMER/TECHNICIAN y sesión ausente, sin exposición de categorías, asientos ni vista previa.
- [ ] T018 [US2] Añadir en tests/unit/application/test_accounting_assistant.py casos de datos faltantes, menos de dos líneas, importe no positivo o en ambos lados, precisión Decimal/PEN y balance desigual; verificar que no se inventan cuentas, IGV o costos.
- [ ] T019 [US2] Añadir en tests/contract/patterns/test_accounting_assistant_contract.py la ausencia de escritura antes del POST de 003, el campo opcional de vista previa y la invariancia de ChatIn sin acción de confirmación contable.
- [ ] T020 [US2] Extender tests/contract/test_accounting_contract.py y tests/integration/test_accounting_api.py para el POST existente de 003: solo ADMIN, nuevo asiento CONFIRMED, Idempotency-Key estable, reintento 200 y conflicto 409 por distinto payload; no duplicar endpoint.
- [ ] T021 [US3] Extender tests/contract/test_accounting_contract.py y tests/integration/test_accounting_api.py para consulta de detalle y reversión con motivo, actor de sesión, original intacto y rechazo de reversión duplicada.
- [ ] T022 [US1] Ejecutar escenarios de contrato equivalentes para los tres patrones en tests/contract/patterns/test_accounting_assistant_contract.py, sin modificar código de Orquestador ni Jerárquico en este worktree; BLOQUEADA para aprobación completa hasta que T015 y sus integraciones externas estén disponibles.

## Phase 8 — Integración PostgreSQL autorizada

**Goal**: verificar la durabilidad real y la atomicidad de 003.

- [ ] T023 [US2] Ejecutar tests/integration/test_accounting_postgres.py en un PostgreSQL de prueba autorizado para comprobar creación confirmada, auditoría, rollback, idempotencia concurrente y reversión; BLOQUEADA hasta disponer del entorno y autorización de ejecución. No correr migraciones sobre bases compartidas ni declarar durabilidad real a partir de sustituciones.

## Dependencies and execution order

T001 → T002 → T003 → T004–T006 → T007–T009 → T010–T012 → T013–T015 → T016 → T017–T022 → T023. Las tareas de consulta US1 y reversión US3 pueden desarrollarse en paralelo después de fijar el contrato común, siempre que no editen los mismos archivos al mismo tiempo. El MVP funcional es US2 en Descentralizado con vista previa, validación y POST de 003 confirmado por ADMIN; la equivalencia completa de 001 requiere T015 y T022.

## Blockers

- **Contrato chat/frontend**: T002 bloquea T003 y T016 hasta acuerdo de responsables de API/chat y frontend; no se les contacta en esta etapa.
- **Otros patrones**: T015/T022 requieren coordinación con sus responsables; este worktree no modifica Orquestador ni Jerárquico.
- **PostgreSQL real**: T023 requiere entorno de prueba autorizado.
- **Decisiones contables**: ninguna tarea de este alcance depende de aprobar cuentas, IGV o costos, porque ADMIN proporciona manualmente las líneas y 003 valida solo estructura y balance. Si se pide derivar importes o cuentas de eventos comerciales, ese trabajo queda bloqueado hasta decisión del líder/equipo contable y queda fuera de 007.
