---
description: "Tareas de implementación para la trazabilidad completa del inventario"
---

# Tasks: Trazabilidad de movimientos de inventario

**Input**: Design documents from `specs/008-trazabilidad-movimientos-inventario/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/inventory-movements.openapi.yaml`, `quickstart.md`

**Tests**: No se agregan tareas para crear ni ejecutar pruebas automatizadas. `quickstart.md` mantiene escenarios para validación manual posterior.

**Organization**: Tareas agrupadas por historia de usuario. Implementación backend; no se modifica frontend.

## Phase 1: Setup

**Purpose**: Establecer la convención para migraciones nuevas del backend.

- [X] T001 Crear `sql/migrations/README.md` con convención de migraciones incrementales versionadas, aplicación explícita por entorno y regla de no tratar dumps de reconstrucción como migraciones.

---

## Phase 2: Foundational

**Purpose**: Definir invariantes compartidos y esquema para bloquear todas las historias.

- [X] T002 [P] Añadir en `app/domain/inventory.py` las reglas puras para delta, conteo físico (entero entre 0 y 999999), motivo de 1 a 500 caracteres y compatibilidad de tipo/signo de movimiento; delta cero solo se permite para `OPENING_BALANCE` del corte.
- [X] T003 [P] Extender `app/application/ports.py`, `app/application/inventory.py` y `app/application/errors.py` con operaciones de apertura, ajuste por conteo e historial, errores tipados de reserva/idempotencia y resultados de movimiento; mantener domain/application libres de FastAPI y SQLAlchemy.
- [X] T004 Crear `sql/migrations/20261108_inventory_movement_traceability.sql` como migración aditiva y transaccional: ampliar `movement_type` a `OPENING_BALANCE`, `ADJUSTMENT_IN`, `ADJUSTMENT_OUT`, `PURCHASE_RECEIPT`, `SALE`; agregar `actor_kind` (`USER`/`SYSTEM`), `reason`, `idempotency_key` y `request_hash`; permitir actor nulo solo en corte SYSTEM; exigir motivo y clave/hash para operaciones manuales; mantener snapshots, FKs de compra/venta, delta/signo/origen y fórmula `stock_after = stock_before + quantity_delta`; añadir unicidad e índices de artículo/fecha; preservar todas las filas existentes.
- [X] T005 Actualizar `sql/esquema-vacio-produccion.sql` con las mismas columnas, restricciones, FKs e índices de la migración de `sql/migrations/20261108_inventory_movement_traceability.sql`, sin convertir el bootstrap en script de migración ni agregar instrucciones destructivas.
- [X] T006 Implementar en `app/adapters/persistence/inventory_movements.py` la operación compartida que, dentro de la transacción del caller, bloquea el artículo, valida saldo/reservas, actualiza `spare_parts.current_stock` e inserta exactamente un movimiento; mantener orden ascendente de locks para operaciones con varias líneas y no revelar SQL/excepciones.

**Checkpoint**: Tipos, errores, migración estructural y escritor transaccional compartido disponibles antes de las historias.

---

## Phase 3: User Story 1 - Registrar aperturas y ajustes de existencias (Priority: P0)

**Goal**: El personal inicia artículos en cero y cambia stock mediante conteo físico con motivo, actor e idempotencia.

**Independent Test**: Crear artículo con stock cero; abrir saldo; aumentar y disminuir por conteo; repetir una clave; intentar bajar de reservas. Consultar artículo y movimientos y verificar saldos, actor y motivo coherentes.

### Implementation for User Story 1

- [X] T007 [P] [US1] Actualizar `specs/005-api-inventario/contracts/inventory.openapi.yaml`; `current_stock` queda opcional y obsoleto por compatibilidad, y el backend lo traduce en movimiento.
- [X] T008 [US1] Modificar `app/adapters/persistence/inventory.py` para crear artículos con `current_stock=0`, quitar stock del reemplazo de catálogo y retirar como inactivo cualquier artículo con movimientos sin perder sus FKs ni snapshots.
- [X] T009 [US1] Implementar en `app/adapters/persistence/inventory.py` aperturas y ajustes con conteo físico y motivo; calcular delta desde saldo bloqueado; rechazar conteo menor que reservas; guardar actor de sesión, hash y clave idempotente; misma clave/hash devuelve replay y misma clave con otro hash produce conflicto.
- [X] T010 [US1] Extender `app/application/inventory.py` y `app/adapters/api/inventory.py` con apertura y ajuste autenticados, esquemas estrictos sin campos extra, `Idempotency-Key`, respuestas para cambio/no-op/replay y errores 401/403/404/409/422/503; mantener `require_staff` para ADMIN/TECHNICIAN.
- [X] T011 [US1] Añadir los contratos OpenAPI de apertura y ajuste en `specs/008-trazabilidad-movimientos-inventario/contracts/inventory-movements.openapi.yaml` con entradas `counted_stock` y `reason`, respuesta de movimiento/saldo, clave idempotente y errores documentados.

---

## Phase 4: User Story 2 - Conservar trazabilidad en compras y ventas (Priority: P0)

**Goal**: Recepciones y ventas siguen generando un único movimiento atómico por línea usando la regla común.

**Independent Test**: Registrar una recepción parcial y confirmar venta de varias líneas; validar que cada línea produce un movimiento por su origen y que fallo o replay no dejan saldo parcial ni duplicado.

### Implementation for User Story 2

- [X] T012 [P] [US2] Reemplazar en `app/adapters/persistence/purchases.py` la actualización directa del stock por la operación común de `app/adapters/persistence/inventory_movements.py`; conservar transacción, recepción parcial, actor, clave/hash y unicidad por `purchase_receipt_item_id`.
- [X] T013 [P] [US2] Reemplazar en `app/adapters/persistence/sales_quotes.py` la actualización directa del stock por la operación común de `app/adapters/persistence/inventory_movements.py`; conservar consumo de reservas, orden de locks, actor, idempotencia y unicidad por `sales_order_item_id`.

---

## Phase 5: User Story 3 - Consultar historial auditable por repuesto (Priority: P1)

**Goal**: Personal autorizado filtra y pagina movimientos incluyendo historia legado, actor, motivo y origen.

**Independent Test**: Consultar un artículo con apertura, ajustes, recepción, venta y movimiento anterior al corte; recorrer filtros y páginas y comprobar orden estable y ausencia de duplicados.

### Implementation for User Story 3

- [X] T014 [US3] Implementar en `app/adapters/persistence/inventory.py` la consulta del historial por artículo con filtro opcional de tipo/fecha, actor, origen, `is_before_cutover`, orden descendente estable por `created_at,id`, total y paginación con máximo 200.
- [X] T015 [US3] Añadir en `app/application/inventory.py` y `app/adapters/api/inventory.py` la consulta autenticada del historial para artículos activos e inactivos; validar filtros y paginación y devolver 401/403/404/422/503 con el formato JSON existente.
- [X] T016 [P] [US3] Completar `specs/008-trazabilidad-movimientos-inventario/contracts/inventory-movements.openapi.yaml` con los parámetros y respuesta paginada del historial, `actor_kind`, responsable, motivo, origen y marca de historia anterior al corte.

---

## Phase 6: User Story 4 - Establecer el punto de corte para el stock existente (Priority: P1)

**Goal**: Dar una base trazable para los saldos actuales preservando los eventos anteriores sin inventar ni sumar dos veces movimientos.

**Independent Test**: Sobre una copia del estado actual, migrar repuestos con stock positivo/cero y movimientos históricos; comprobar una apertura SYSTEM por artículo, conservación del movimiento legado, reejecución sin duplicados y saldo reconciliable posterior.

### Implementation for User Story 4

- [X] T017 [US4] Completar `sql/migrations/20261108_inventory_movement_traceability.sql` con el corte bajo bloqueo de escrituras: calcular dinámicamente cada saldo vigente, insertar apertura `OPENING_BALANCE` SYSTEM desde cero (delta igual al saldo; cero permitido solo en esta apertura), preservar el movimiento legado, identificar filas anteriores al corte y asegurar unicidad/repetibilidad sin valores fijos del estado observado.
- [X] T018 [US4] Documentar en `sql/migrations/README.md` el orden de aplicación, precondiciones, verificación de versión/esquema destino, ventana para serializar escrituras, validación de conteos y recuperación segura; indicar expresamente que `contexto/tablas postgres v2.sql` no es migración.
- [X] T019 [US4] Actualizar `specs/008-trazabilidad-movimientos-inventario/quickstart.md` con el procedimiento y resultado esperado del corte real, la preservación de historia legado y verificación manual de saldos, sin depender del conteo 431/2618 de la inspección actual.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Completar la documentación funcional y comprobar manualmente los flujos backend descritos.

- [X] T020 [P] Actualizar `docs/24-api-inventario.md`, `docs.md` y `features.md` para describir el stock de solo lectura en CRUD, apertura/ajuste, historial y política de retiro con trazabilidad.
- [ ] T021 Recorrer `specs/008-trazabilidad-movimientos-inventario/quickstart.md` en la BD de prueba, revisar saldo/movimientos después de cada flujo y registrar resultados sin exponer datos personales ni credenciales.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencias.
- **Foundational (Phase 2)**: depende de Setup y bloquea todas las historias.
- **US1 (Phase 3)**: depende de Foundation; habilita apertura/ajuste para artículos nuevos.
- **US2 (Phase 4)**: depende del escritor compartido de Foundation; puede desarrollarse en paralelo con US1 en archivos separados.
- **US3 (Phase 5)**: depende de Foundation y del formato final de movimiento; conviene después de US1/US2 porque consulta todos sus tipos.
- **US4 (Phase 6)**: depende del esquema de Foundation; el corte debe ejecutarse antes de habilitar las nuevas operaciones en una BD con datos existentes.
- **Polish (Phase 7)**: depende de US1–US4.

### User Story Dependencies

- **US1 (P0)**: Foundation completa; independiente de US2.
- **US2 (P0)**: Foundation completa; tareas T012 y T013 pueden ir en paralelo.
- **US3 (P1)**: requiere tipos y fuentes de movimientos definidos en Foundation/US1/US2.
- **US4 (P1)**: requiere esquema ampliado de Foundation; es puerta obligatoria para despliegue sobre la BD existente, aunque su fase aparezca después por prioridad de historia.

### Parallel Opportunities

- T002 y T003 pueden prepararse en paralelo tras revisar contratos.
- T007 puede avanzar en paralelo con T008 antes de integrar endpoints.
- T012 y T013 pueden desarrollarse en paralelo tras T006, pues modifican repositorios distintos.
- T016 y tareas de consulta API pueden prepararse en paralelo, sin duplicar `contracts/inventory-movements.openapi.yaml`.

## Parallel Example: User Story 2

```text
Task: T012 — integrar movimientos de recepción en app/adapters/persistence/purchases.py
Task: T013 — integrar movimientos de venta en app/adapters/persistence/sales_quotes.py
```

## Implementation Strategy

### MVP

Implementar primero Foundation y US1 para eliminar el bypass de stock en alta/edición y habilitar operaciones explícitas. Completar US2 antes de considerar satisfecho P0: mientras compras o ventas no usen la regla común no se cumple “toda variación deja movimiento”. US4 es requisito de despliegue sobre datos existentes.

### Entrega incremental

1. Foundation: restricciones y helper transaccional compartido.
2. US1: catálogo sin escritura de stock, apertura y ajuste.
3. US2: conectar recepción y venta al mismo helper.
4. US3: lectura auditable y paginada.
5. US4: corte dinámico y reejecutable antes de desplegar sobre BD existente.
6. Polish: actualizar documentación y recorrer quickstart en BD de prueba.

## Notes

- Cada tarea incluye rutas concretas; `[P]` marca únicamente cambios en archivos independientes.
- No se incluyen tareas para crear o ejecutar tests, porque no se solicitó TDD ni validación automatizada en este pedido.
- El estado de BD leído ahora es solo referencia; la migración siempre consulta saldos actuales al momento de ejecutarse.
- No ejecutar la migración ni desplegar la característica desde esta fase de generación de tareas.


