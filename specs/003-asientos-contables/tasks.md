---
description: "Tareas backend para registro y trazabilidad de asientos contables"
---

# Tasks: Registro y trazabilidad de asientos contables

**Input**: Documentos de diseño en `specs/003-asientos-contables/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/accounting.openapi.yaml`, `quickstart.md`

**Tests**: Incluidos porque los criterios de aceptación requieren validar autorización, balance, idempotencia, transacciones y concurrencia. Escribir las pruebas de cada historia antes de su implementación.

**Organización**: Las tareas se agrupan por historia del usuario. El alcance es exclusivamente el repositorio backend.

## Phase 1: Setup

**Purpose**: Preparar el aislamiento de las pruebas PostgreSQL sin usar por defecto la conexión de `.env`.

- [X] T001 Añadir en `tests/integration/conftest.py` una fixture contable que requiera explícitamente `ACCOUNTING_TEST_DATABASE_URL`, no haga fallback a `DATABASE_URL` y permita omitir las pruebas PostgreSQL cuando la variable no está configurada.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Autorizar personal administrativo y establecer persistencia/puertos compartidos antes de habilitar las historias.

### Tests first

- [X] T002 [P] Añadir en `tests/integration/test_session_guard.py` pruebas para `require_admin`: sesión ADMIN activa permitida; sesión CUSTOMER/TECHNICIAN recibe 403; sesión ausente, inválida o usuario desactivado recibe 401.
- [X] T003 [P] Crear en `tests/integration/test_accounting_postgres.py` pruebas de migración, claves foráneas, constraints por línea, balance diferido, unicidad del correlativo y ausencia de reversión duplicada, usando solo `ACCOUNTING_TEST_DATABASE_URL`.

### Implementation

- [X] T004 [P] Añadir `SessionGuard.require_admin` en `app/accounts/session.py`, reutilizando `require_user` y el rol `ADMIN`; no cambiar `require_customer` ni la cookie existente.
- [X] T005 [P] Crear `sql/migrations/003_accounting_entries.sql` como migración aditiva con `accounting_categories`, `accounting_entries`, `accounting_entry_lines` y `accounting_audit_events`; añadir categorías internas `SALE`, `SERVICE`, `PURCHASE`, `OPERATING_EXPENSE`, `ADJUSTMENT`, `OTHER`; imponer `currency = PEN`, `status IN (CONFIRMED, REVERSED)`, `debit_total`/`credit_total NUMERIC(14,2) > 0`, FK con `ON DELETE RESTRICT`, `UNIQUE(responsible_user_id, idempotency_key)`, correlativo global único y `UNIQUE(reversal_of_entry_id)`; guardar `created_at` y `updated_at` UTC; limitar `concept` a 200, `detail` a 4000, `account_code` a 40, `account_name` a 200, descripción de línea a 1000 y razón de reversión a 2000 caracteres; imponer importe no negativo y exactamente un lado positivo por línea, 2–100 líneas y balance/totales con trigger diferido; preservar auditoría append-only y crear los índices descritos en `data-model.md`.
- [X] T006 [P] Añadir en `app/application/ports.py` el puerto del repositorio contable y en `app/application/errors.py` errores seguros para validación, conflicto, registro inexistente e indisponibilidad de persistencia.
- [X] T007 Aplicar y verificar `sql/migrations/003_accounting_entries.sql` únicamente en la base aislada indicada por `ACCOUNTING_TEST_DATABASE_URL`; registrar tablas/índices previos y posteriores, resultado y limitaciones en `docs/21-asientos-contables.md`.

**Checkpoint**: Guard ADMIN, migración y puertos están disponibles; ninguna prueba escribe contra `.env` ni una base de producción.

---

## Phase 3: User Story 1 - Registrar un asiento balanceado (Priority: P1) 🎯 MVP

**Goal**: Crear y confirmar en una sola operación un asiento en PEN cuyo actor sea el ADMIN autenticado y cuyas líneas balanceen.

**Independent Test**: `POST /api/admin/accounting/entries` con sesión ADMIN, `Idempotency-Key` UUID y al menos dos líneas balanceadas devuelve 201 y un detalle completo; un usuario sin permiso o un asiento inválido no crea filas.

### Tests for User Story 1

> Escribir y ejecutar estas pruebas antes de implementar la historia; comprobar que fallan por ausencia de la capacidad.

- [X] T008 [P] [US1] Crear `tests/unit/domain/test_accounting.py` para importes `Decimal`, líneas positivas en exactamente un lado y balance exacto; rechazar menos de 2 o más de 100 líneas, código de cuenta >40, denominación >200, descripción de línea >1000, concepto >200 o detalle >4000 caracteres.
- [X] T009 [P] [US1] Crear `tests/unit/application/test_accounting.py` y `tests/unit/adapters/test_accounting_repository.py` para alta confirmada, identidad derivada del actor, conversión de filas y montos, clave idempotente repetida con mismo hash y conflicto cuando se reutiliza con payload distinto.
- [X] T010 [P] [US1] Crear `tests/integration/test_accounting_api.py` para alta 201, replay 200, errores 401/403/409/422/503, cuenta/categoría inactiva y rollback sin filas parciales.
- [X] T011 [P] [US1] Crear `tests/contract/test_accounting_contract.py` para verificar que `POST /api/admin/accounting/entries` y `GET /api/admin/accounting/categories` coinciden con `specs/003-asientos-contables/contracts/accounting.openapi.yaml`, incluido `Idempotency-Key`.

### Implementation for User Story 1

- [X] T012 [US1] Implementar valores y reglas en `app/domain/accounting.py`: moneda PEN; código de cuenta 1–40; denominación 1–200; concepto 1–200; detalle 1–4000; 2–100 líneas; descripción de línea opcional ≤1000; razón de reversión 1–2000; `Decimal` con dos decimales y precisión compatible con `NUMERIC(14,2)`; cada línea tiene debe o haber positivo, nunca ambos; debe total = haber total >0.
- [X] T013 [US1] Implementar el caso `CreateAccountingEntry` en `app/application/accounting.py` y extender `AccountingRepository` en `app/application/ports.py` para validar categoría activa, calcular SHA-256 del payload canónico y devolver el mismo asiento ante reintento idéntico.
- [X] T014 [US1] Implementar en `app/adapters/persistence/accounting.py` la lectura de categorías activas y la creación transaccional del encabezado, líneas y evento `ENTRY_CREATED`; obtener actor de sesión; usar restricción `(responsible_user_id, idempotency_key)`; no escribir si falla cualquier parte.
- [X] T015 [US1] Implementar en `app/adapters/api/accounting.py` los esquemas y rutas `GET /api/admin/accounting/categories` y `POST /api/admin/accounting/entries`; exigir `require_admin`, `Idempotency-Key` UUID, devolver importes como cadenas y mapear errores según OpenAPI.
- [X] T016 [US1] Registrar el router contable en `app/infrastructure/chat_app.py` y añadir `Idempotency-Key` a `CORSMiddleware.allow_headers`; conservar `GET`/`POST` y el comportamiento de chat/cuentas.

**Checkpoint**: El MVP crea un asiento confirmado de forma atómica, balanceada e idempotente sin depender del frontend.

---

## Phase 4: User Story 2 - Consultar y presentar el detalle (Priority: P2)

**Goal**: Listar, filtrar y recuperar el detalle necesario para que el frontend independiente presente un asiento y su trazabilidad.

**Independent Test**: Con registros de prueba, un ADMIN lista por fecha/categoría/estado/correlativo y consulta un asiento; el detalle contiene encabezado, líneas ordenadas, totales, categoría, responsable, fechas, eventos y relación de reversión.

### Tests for User Story 2

- [X] T017 [P] [US2] Extender `tests/contract/test_accounting_contract.py` con respuestas paginadas, filtros, decimal serializado como texto, detalle y errores 404/422 según `accounting.openapi.yaml`.
- [X] T018 [P] [US2] Extender `tests/integration/test_accounting_api.py` para `GET /api/admin/accounting/entries` y `GET /api/admin/accounting/entries/{entry_id}`, incluyendo paginación por defecto 50/máximo 100, filtros, listado vacío, orden de líneas, historial, 404 y 401/403.

### Implementation for User Story 2

- [X] T019 [US2] Implementar consultas paginadas y filtros `from_date`, `to_date`, `category_id`, `status` y `entry_number` en `app/adapters/persistence/accounting.py`; limitar `limit` a 1–100 y devolver total más offset.
- [X] T020 [US2] Implementar `ListAccountingEntries` y `GetAccountingEntry` en `app/application/accounting.py`, ensamblando categoría, responsable, líneas por `line_number`, eventos por fecha y vínculo de reversión.
- [X] T021 [US2] Implementar en `app/adapters/api/accounting.py` `GET /api/admin/accounting/entries` y `GET /api/admin/accounting/entries/{entry_id}`; devolver `entry_number` como texto, montos PEN con dos decimales y fechas UTC/ISO.

**Checkpoint**: Un ADMIN puede localizar y obtener en una sola consulta todos los datos requeridos para la vista de detalle del frontend.

---

## Phase 5: User Story 3 - Revertir un asiento confirmado (Priority: P3)

**Goal**: Corregir una operación mediante un asiento inverso relacionado, manteniendo inmutable la información contable original.

**Independent Test**: Revertir un asiento una vez produce un asiento confirmado con debe/haber intercambiados, actor/fecha/razón y relaciones auditables; un reintento igual devuelve el mismo resultado y una segunda reversión distinta recibe 409.

### Tests for User Story 3

- [X] T022 [P] [US3] Extender `tests/unit/domain/test_accounting.py` para invertir los lados de cada línea, conservar total/categoría y rechazar razón vacía o asiento ya revertido.
- [X] T023 [P] [US3] Extender `tests/integration/test_accounting_postgres.py` para probar reversión atómica, una sola reversión bajo concurrencia, constraint único, estado original `REVERSED` y que líneas/auditoría no se alteren si la operación falla.
- [X] T024 [P] [US3] Extender `tests/contract/test_accounting_contract.py` con `POST /api/admin/accounting/entries/{entry_id}/reverse`, 201/200/401/403/404/409/422/503 y el esquema `ReversalResult`.

### Implementation for User Story 3

- [X] T025 [US3] Implementar `ReverseAccountingEntry` en `app/application/accounting.py`: exigir fecha y razón de 1–2000 caracteres, bloquear la repetición y devolver el recurso existente solo si fecha y razón coinciden.
- [X] T026 [US3] Implementar en `app/adapters/persistence/accounting.py` la reversión en una sola transacción: bloquear original, crear líneas intercambiadas y nuevo asiento `CONFIRMED`, registrar `REVERSAL_CREATED`/`ENTRY_REVERSED`, marcar el original `REVERSED` y resolver reintentos/concurrencia.
- [X] T027 [US3] Implementar `POST /api/admin/accounting/entries/{entry_id}/reverse` en `app/adapters/api/accounting.py`; exigir ADMIN, validar request, devolver `ReversalResult` y mapear segunda reversión o payload distinto a 409.

**Checkpoint**: El original sigue consultable e inmutable; la reversión es una operación única, atómica y trazable.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Actualizar documentación y verificar seguridad, contrato y regresiones del backend.

- [X] T028 [P] Actualizar `features.md`, `docs.md` y `memory.md` con rutas, rol ADMIN, estado real de la migración y resultados de pruebas; completar la evidencia `docs/21-asientos-contables.md` sin incluir URL de BD, credenciales ni datos personales.
- [X] T029 [P] Actualizar `specs/003-asientos-contables/quickstart.md` con la orden exacta para aplicar la migración solo a `ACCOUNTING_TEST_DATABASE_URL`, ejecutar escenarios y resultados esperados.
- [X] T030 Revisar `app/adapters/api/accounting.py`, `app/adapters/persistence/accounting.py` y `sql/migrations/003_accounting_entries.sql` para confirmar que ninguna ruta customer/LLM escribe, ninguna traza expone datos sensibles, y que `CUSTOMER`/`TECHNICIAN` reciben 403.
- [X] T031 Ejecutar pruebas unitarias/contrato/API contables y suite aislada configurada en `pytest.ini`; ejecutar `python -m compileall app` y `git diff --check`; registrar fallos preexistentes sin ampliar su alcance.
- [X] T032 Ejecutar los escenarios de `specs/003-asientos-contables/quickstart.md` en la base de prueba autorizada; comparar tablas antes/después, verificar idempotencia, rollback, balance y concurrencia, y anotar evidencia en `docs/21-asientos-contables.md`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 establece que las pruebas PostgreSQL solo usan conexión explícita de prueba.
- **Foundational (Phase 2)**: T002–T003 se escriben primero; T004–T006 implementan guard, migración y puertos; T007 aplica/verifica la migración. Todo bloquea las historias.
- **US1 (Phase 3)**: pruebas T008–T011 antes de T012–T016; entrega el alta de asientos confirmados.
- **US2 (Phase 4)**: depende de US1 para compartir encabezado, adaptador y router; pruebas T017–T018 antes de T019–T021.
- **US3 (Phase 5)**: depende de US1 y de las entidades consultables de US2; pruebas T022–T024 antes de T025–T027.
- **Polish (Phase 6)**: depende de las tres historias; T031 y T032 son validaciones finales.

### User Story Dependencies

- **US1 (P1)**: requiere Setup + Foundational; no depende de US2/US3.
- **US2 (P2)**: requiere el repositorio/router de US1; puede validarse con fixtures de US1.
- **US3 (P3)**: requiere asiento persistido de US1 y detalle consultable; no cambia la lógica de patrones multiagente.

### Parallel Opportunities

- T002 y T003 pueden escribirse en paralelo después de T001; T004/T005/T006 son archivos separados después de esas pruebas.
- Dentro de US1, T008–T011 pueden escribirse en paralelo por archivo; la implementación T012–T016 se mantiene ordenada por dominio → aplicación → persistencia → API/composición.
- En US2, T017 y T018 son paralelizables; las tareas de implementación se mantienen secuenciales porque extienden los mismos módulos.
- En US3, T022–T024 son paralelizables; T025–T027 dependen del modelo y repositorio existentes.
- T028 y T029 pueden ejecutarse en paralelo con revisiones de contrato una vez concluidas las historias.

## Parallel Example: User Story 1

```text
T008 tests/unit/domain/test_accounting.py
T009 tests/unit/application/test_accounting.py
T010 tests/integration/test_accounting_api.py
T011 tests/contract/test_accounting_contract.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Completar T001–T007: aislamiento de pruebas, autorización ADMIN y migración trazable.
2. Completar T008–T016: alta balanceada/idempotente y categorías disponibles.
3. Validar US1 por separado antes de construir listado/detalle o reversión.

### Incremental Delivery

1. Entregar US1: crear un asiento confirmado de forma segura.
2. Entregar US2: listar/filtrar y devolver todos los datos del detalle para el frontend.
3. Entregar US3: corrección mediante reversión vinculada.
4. Cerrar con T028–T032; no incluir UI frontend, PLE ni contabilización automática de pagos.
