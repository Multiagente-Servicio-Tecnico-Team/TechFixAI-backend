---

description: "Dependency-ordered implementation tasks for accounting catalog and reports"
---

# Tasks: Catálogo de cuentas y consultas contables

**Input**: Design documents from `specs/009-catalogo-cuentas-consultas-contables/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/accounting-catalog.openapi.yaml`, `quickstart.md`

**Tests**: No se agregan tareas para crear o ejecutar pruebas automatizadas porque no se solicitó TDD ni una corrida de pruebas. Cada fase mantiene su criterio de validación independiente; `quickstart.md` contiene los escenarios para la verificación posterior.

**Organization**: Tasks are grouped by user story. The shared additive schema and PCGE seed are foundational because the stories depend on them.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede trabajarse en paralelo porque usa archivos distintos y no depende de una tarea incompleta.
- **[Story]**: Relación con una historia de `spec.md` (`US1` a `US5`).
- Las tareas incluyen archivos exactos del backend; los archivos de migración indican la siguiente versión verificada cuando esta depende del ledger.

## Phase 1: Setup

**Purpose**: Preparar la dependencia XLSX y reconciliar el control de versiones de esquema antes de crear migraciones.

- [X] T001 [P] Agregar y fijar la dependencia `openpyxl` en `requirements.txt`; no añadir Pandas ni cambiar las demás dependencias.
- [X] T002 [P] Inspeccionar el ledger de la base de prueba y reconciliar la versión `011` con el archivo `sql/migrations/011_inventory_movement_traceability.sql`; comprobar checksum y formato que acepta `app/database/migrations.py`, preservar bytes y checksums aplicados, y documentar el resultado en `sql/migrations/README.md`.

---

## Phase 2: Foundational

**Purpose**: Crear la base compartida de catálogo, periodos, auditoría e inmutabilidad. Todas las historias dependen de esta fase.

- [X] T003 [P] Definir los tipos y validaciones compartidos de plan, cuenta y periodo en `app/domain/accounting.py`, incluyendo `normal_balance` `DEBIT|CREDIT`, estados `ACTIVE|INACTIVE` y `OPEN|CLOSED`, unicidad de código por plan, padre dentro del mismo plan, jerarquía sin ciclos y condición de cuenta imputable.
- [X] T004 [P] Crear una migración aditiva `sql/migrations/012_accounting_catalog_schema.sql` con la siguiente versión secuencial confirmada en T002: agregar planes, cuentas, periodos y eventos de auditoría; `accounting_entries.accounting_plan_id` y `accounting_entry_lines.account_id` son nullable para legado; `accounting_plans` tiene identidad única `(code, edition)` y a lo sumo un plan predeterminado activo; `accounting_accounts` tiene código único `(plan_id, code)`, padre opcional del mismo plan, jerarquía sin ciclos, `normal_balance` `DEBIT|CREDIT`, `is_postable`, estado `ACTIVE|INACTIVE` y vigencia; `accounting_periods` tiene unicidad `(year, month)` y estado `OPEN|CLOSED`; conservar snapshots obligatorios, triggers de balance/inmutabilidad, FKs RESTRICT, importes e IDs; agregar índices del `data-model.md`.
- [X] T005 Crear una migración de seed `sql/migrations/013_seed_pcge_modificado_2019.sql` con la siguiente versión posterior a T004: cargar el PCGE Modificado 2019 desde la fuente oficial MEF con edición, fuente, vigencia, jerarquía, naturaleza/saldo normal y condición imputable validados; fijar este plan como predeterminado sin crear asientos ficticios.
- [X] T006 Actualizar `sql/esquema-vacio-produccion.sql` para que el esquema de reconstrucción incluya las nuevas entidades, restricciones, índices y el catálogo PCGE base; mantener explícito que es bootstrap y no una migración.
- [X] T007 [P] Implementar en `app/adapters/persistence/accounting.py` y `app/application/accounting.py` la creación/lectura transaccional del periodo abierto al primer uso y el bloqueo común que serializa la creación/reversión de asientos con el cierre/reapertura del mismo mes.

**Checkpoint**: El esquema aditivo, el plan PCGE predeterminado y las reglas de periodo compartidas están disponibles; las historias pueden continuar sin cambiar los asientos históricos.

---

## Phase 3: User Story 1 - Consultar y administrar planes de cuentas (Priority: P1)

**Goal**: ADMIN consulta el PCGE predeterminado y puede crear planes alternativos y administrar cuentas jerárquicas sin reescribir el historial.

**Independent Test**: Con ADMIN, listar PCGE y sus metadatos; crear un plan/cuentas; comprobar código duplicado, jerarquía inválida y cambios al plan predeterminado se validan y auditan.

- [X] T008 [US1] Implementar reglas en `app/domain/accounting.py` para plan con `code` y `edition` únicos, una sola opción `is_default` activa, cuentas con `plan_id` obligatorio, `code` único por plan, `parent_account_id` solo del mismo plan, sin ciclos, `normal_balance` `DEBIT|CREDIT`, `status` `ACTIVE|INACTIVE`, vigencia válida y `is_postable` solo cuando no tenga descendientes; una cuenta referenciada se desactiva, nunca se elimina físicamente.
- [X] T009 [P] [US1] Implementar en `app/adapters/persistence/accounting.py` operaciones paginadas por `plan_id`, código, nombre, padre, `is_postable` y `status`; persistir `jurisdiction`, `edition`, `source_name`, `source_url`, `effective_from/effective_to`, actor y timestamps; impedir duplicados y cambios al snapshot de asientos.
- [X] T010 [US1] Añadir los casos de uso de catálogo y selección del plan predeterminado en `app/application/accounting_catalog.py`, derivando el actor del ADMIN autenticado.
- [X] T011 [US1] Añadir a `app/adapters/api/accounting_catalog.py` operaciones ADMIN para listar/crear planes, fijar plan predeterminado, listar/crear/actualizar/desactivar cuentas y consultar eventos de auditoría; validar filtros y errores sin exponer SQL.
- [X] T012 [P] [US1] Alinear `specs/009-catalogo-cuentas-consultas-contables/contracts/accounting-catalog.openapi.yaml` con los contratos de planes/cuentas del router, paginación, permisos, conflictos y respuestas de auditoría.

**Checkpoint**: Catálogo y planes alternativos funcionan independientemente del registro de nuevos asientos.

---

## Phase 4: User Story 2 - Registrar asientos con cuentas del plan (Priority: P1)

**Goal**: Un asiento nuevo solo usa cuentas catalogadas, activas, imputables y del mismo plan; el detalle y la reversión conservan cuenta y snapshot.

**Independent Test**: Crear un asiento balanceado y su reversión en un periodo abierto; consultar ambos y comprobar `account_id`, código/nombre snapshot y debe/haber. Un código no catalogado o cuenta inválida no deja escritura parcial.

- [X] T013 [P] [US2] Actualizar `EntryLineIn` y `CreateEntryIn` en `app/adapters/api/accounting.py` para aceptar `account_id` preferido y, durante la transición del frontend existente, resolver `account_code` exacto en el plan predeterminado; aceptar `account_name` legado solo como dato ignorado, resolver el nombre desde el catálogo y permitir `plan_id` explícito u omisión con resolución del predeterminado.
- [X] T014 [US2] Actualizar `EntryLine`, `EntryDraft` y sus validaciones en `app/domain/accounting.py` para exigir al menos dos líneas, exactamente un lado positivo por línea, suma debe/haber exacta y cuentas imputables de un único plan activo.
- [X] T015 [P] [US2] Implementar resolución de cuentas y transacción de creación en `app/application/accounting.py` y `app/adapters/persistence/accounting.py`: validar plan, cuenta y periodo abierto; guardar IDs y snapshots; conservar idempotencia y atomicidad.
- [X] T016 [US2] Actualizar `reverse_entry` en `app/adapters/persistence/accounting.py` para copiar `accounting_plan_id`, `account_id`, código/nombre snapshot y línea a la reversión, respetando el periodo abierto y sin cambiar el asiento original.
- [X] T017 [P] [US2] Actualizar los contratos de creación, detalle y reversión en `specs/003-asientos-contables/contracts/accounting.openapi.yaml` y `specs/009-catalogo-cuentas-consultas-contables/contracts/accounting-catalog.openapi.yaml`, incluyendo resolución transitoria de código exacto, snapshot de respuesta y errores `409/422` por periodo/cuenta.

**Checkpoint**: Los nuevos asientos se validan contra catálogo y los clientes antiguos solo pueden crear líneas si su código coincide exactamente con una cuenta habilitada.

---

## Phase 5: User Story 3 - Gestionar periodos contables mensuales (Priority: P1)

**Goal**: ADMIN puede listar, cerrar y reabrir meses con razón de reapertura y auditoría, y las escrituras no cruzan un cierre concurrente.

**Independent Test**: Cerrar un mes, comprobar rechazo de una creación/reversión fechada en ese periodo, reabrirlo con motivo y verificar las dos transiciones y sus actores/fechas.

- [X] T018 [US3] Implementar reglas en `app/domain/accounting.py` para periodo mensual con unicidad `(year, month)`, estados `OPEN|CLOSED`, creación OPEN al primer uso, transiciones no repetibles y motivo obligatorio no vacío al reabrir.
- [X] T019 [P] [US3] Implementar cierre/reapertura atómicos en `app/adapters/persistence/accounting.py`, bloqueando el mismo periodo que usa la creación/reversión y registrando `entity_type/id`, acción, actor, timestamp, estado anterior/nuevo y motivo de reapertura como eventos append-only.
- [X] T020 [P] [US3] Añadir en `app/application/accounting.py` y `app/adapters/api/accounting.py` los casos de uso y rutas ADMIN para listar periodos, cerrar/reabrir por año/mes y consultar todo el historial del periodo; devolver conflictos claros para fechas cerradas.
- [X] T021 [US3] Completar `specs/009-catalogo-cuentas-consultas-contables/contracts/accounting-catalog.openapi.yaml` con payload de reapertura, historia auditada, estados, paginación y errores de transición.

**Checkpoint**: Periodos y escrituras contables se coordinan transaccionalmente; reabrir nunca elimina el evento de cierre previo.

---

## Phase 6: User Story 4 - Consultar y exportar reportes contables (Priority: P1)

**Goal**: ADMIN obtiene diario, mayor y balance de comprobación con los mismos filtros y cifras en JSON, CSV y XLSX.

**Independent Test**: Para un rango con asientos y reversión, comparar diario, mayor y balance; verificar saldos/totales y exportaciones CSV/XLSX con mismas filas y sin omisión silenciosa.

- [X] T022 [P] [US4] Crear cálculos puros de reportes en `app/domain/accounting_reports.py`: orden estable, saldo inicial/running balance por naturaleza, apertura/débitos/créditos/cierre del balance y filas históricas sin naturaleza marcadas como desconocidas.
- [X] T023 [P] [US4] Añadir a `app/adapters/persistence/accounting.py` consultas consistentes para diario, mayor y balance, con rango inclusivo, filtros y orden determinista; incluir originales y reversiones una vez, además de líneas legacy por snapshot.
- [X] T024 [P] [US4] Crear `app/adapters/exports/accounting_reports.py` para serializar el mismo iterador ordenado a CSV UTF-8 con BOM y XLSX mediante `openpyxl` write-only; incluir periodo, filtros y totales, fijar tope de 10 000 filas y rechazar exceso sin truncar.
- [X] T025 [US4] Crear `app/application/accounting_reports.py` y añadir a `app/adapters/api/accounting.py` los endpoints ADMIN de diario, mayor y balance con filtros `from_date/to_date`, `plan_id`, cuenta, paginación JSON, formatos `csv|xlsx` y respuesta `413` al superar el límite.
- [X] T026 [P] [US4] Completar `specs/009-catalogo-cuentas-consultas-contables/contracts/accounting-catalog.openapi.yaml` con filtros, esquemas JSON, formatos de descarga, paginación, límites y errores de reportes.

**Checkpoint**: Los tres reportes concilian para el mismo conjunto y sus dos formatos de archivo corresponden a la consulta filtrada.

---

## Phase 7: User Story 5 - Migrar y consultar el historial existente (Priority: P2)

**Goal**: Asientos previos al catálogo siguen íntegros y aparecen en detalle/reportes como históricos no vinculados, sin asignaciones automáticas.

**Independent Test**: Antes y después de aplicar el cambio a la base de prueba, comparar IDs, importes, snapshots, fechas, responsables, estados y reversiones; confirmar que cada `account_id` histórico sigue NULL y los reportes lo muestran por snapshot.

- [X] T027 [US5] Actualizar detalle/listado en `app/adapters/persistence/accounting.py` y `app/adapters/api/accounting.py` para mantener `accounting_plan_id=NULL` y `account_id=NULL` en líneas legadas, conservar `account_code/account_name` como snapshots obligatorios y marcar la línea legacy sin resolver por coincidencia de texto.
- [X] T028 [US5] Aplicar manualmente las migraciones ya verificadas a la base de prueba autorizada, comparar antes/después las filas contables y relaciones del `sql/esquema-vacio-produccion.sql`, y registrar cada versión/checksum confirmados mediante `app/database/migrations.py` solo después de verificar el esquema.
- [X] T029 [US5] Actualizar `specs/009-catalogo-cuentas-consultas-contables/quickstart.md` y `sql/migrations/README.md` con preflight, aplicación explícita, verificación del catálogo y procedimiento de conservación de líneas legacy; no documentar bootstrap como actualización de una base existente.

**Checkpoint**: Historial anterior conserva todos los valores y reportes lo incluyen sin inferir cuenta o naturaleza.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Alinear contratos, despliegue y documentación para backend y siguiente fase frontend.

- [X] T030 Revisar autorización ADMIN, errores `401/403/409/413/422/503`, auditoría y ausencia de secretos en mensajes/trazas en `app/adapters/api/accounting.py`, `app/application/accounting.py` y `app/adapters/persistence/accounting.py`.
- [X] T031 Documentar en `specs/009-catalogo-cuentas-consultas-contables/quickstart.md` la dependencia de selector frontend separado: durante transición solo se acepta el código exacto de una cuenta vigente y el nombre lo resuelve backend.
- [X] T032 Actualizar `docs/27-propuesta-mejoras-backend-basadas-dolibarr.md` marcando el catálogo y los tres reportes como implementados solo después de completar las fases y verificar la base de prueba.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 y T002 pueden hacerse en paralelo; T002 debe terminar antes de asignar versiones de migración.
- **Foundational (Phase 2)**: depende de T002 para las migraciones. T003 puede avanzar en paralelo con T004; T005 depende de T004; T006 depende de T004 y T005; T007 depende de T004. Esta fase bloquea historias.
- **User Stories**: seguir el orden previsto para minimizar conflictos en los mismos módulos y mantener contratos coherentes. Los entregables de una historia se pueden validar independientemente según su criterio.
- **Polish (Phase 8)**: depende de las historias seleccionadas y la verificación de la base de prueba.

### User Story Dependencies

- **US1 (P1)**: depende de Phase 2; habilita catálogo y plan predeterminado.
- **US2 (P1)**: depende de Phase 2 y US1; se apoya en resolución de cuenta y plan.
- **US3 (P1)**: depende de Phase 2 y del guard de periodo; puede desarrollarse después de US2 para evitar colisiones en archivos compartidos.
- **US4 (P1)**: depende de US1, US2 y US3 para agrupar por cuenta, incluir snapshots y respetar estados.
- **US5 (P2)**: depende de la migración fundamental; verifica compatibilidad legacy y base existente sin forzar backfill.

### Parallel Opportunities

- T001 y T002 son independientes.
- T003 puede desarrollarse mientras se prepara T004, tras acordar el modelo del spec.
- En US1, T012 (contrato) puede avanzar en paralelo con reglas/consulta si no se cambia el contrato acordado.
- En US2, T015 y T017 pueden avanzarse en paralelo una vez definidos los nombres de entrada/salida; T016 espera el cambio de persistencia.
- En US4, T026 (contrato) puede avanzarse en paralelo con T022-T024; T025 integra después los componentes.

### Implementation Strategy

**MVP recomendado**: Phase 2 + US1 + US2 + US3. Esto deja el plan PCGE disponible, permite registrar/revertir asientos con cuentas válidas y evita escrituras en periodos cerrados. US4 agrega los reportes/exportaciones; US5 confirma integridad de datos existentes.

**Entrega incremental**:

1. Reconciliar migraciones, agregar schema/seed y catálogo ADMIN.
2. Conectar cuentas a asientos y reversiones, manteniendo compatibilidad temporal segura.
3. Cerrar/reabrir periodos con auditoría.
4. Publicar reportes y exportaciones.
5. Verificar migración sobre datos legacy en base de prueba y actualizar guía.

## Notes

- No se agregaron tareas de prueba automatizada por no haber sido solicitadas; los criterios independientes se especifican para cada historia.
- `[P]` solo marca tareas con archivos separados y sin dependencias pendientes.
- La numeración 012/013 se asignó después de confirmar el ledger 006–011. Los checksums aplicados se registraron tras verificar esquema y seed.
- El usuario confirmó `multiagentedb` como base de prueba permanente para esta sesión; no imprimir ni guardar su URL. El esquema de reconstrucción no reemplaza la migración incremental.


**Estado de ejecución:** 012 y 013 se aplicaron y registraron en la base de prueba `multiagentedb`. El conteo antes/después conserva 2 asientos, 4 líneas y 2 eventos; las columnas nuevas siguen NULL para ese historial. Se verificaron 1192 cuentas, jerarquía completa, una opción predeterminada activa y ausencia de cuentas imputables sin saldo normal o con hijos. Los triggers de inmutabilidad de asientos/líneas continúan deshabilitados por la solicitud previa del usuario; no se reactivaron. No se ejecutaron pruebas automatizadas. La naturaleza/saldo normal del PCGE es una clasificación inicial inferida y requiere validación contable.
