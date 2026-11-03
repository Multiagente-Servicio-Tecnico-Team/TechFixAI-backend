# Tasks: Registro de compras a proveedores

**Input**: Documentos de diseño de `specs/006-registro-compras-proveedores/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/purchases.openapi.yaml`, `quickstart.md`

**Tests**: El spec define pruebas independientes y escenarios de aceptación, pero no solicita explícitamente tareas para crear pruebas automatizadas. Esta lista no añade tareas de pruebas; cada historia conserva su criterio de validación funcional y `quickstart.md` describe la verificación posterior.

**Organization**: Las tareas se agrupan por historia de usuario y prioridad del spec.

## Phase 1: Setup

**Purpose**: Preparar la persistencia versionada sin alterar las tablas existentes destructivamente.

- [x] T001 Crear migración aditiva PostgreSQL en `sql/migrations/005_supplier_purchases.sql`: ampliar `suppliers` conservando campos actuales; crear compras, líneas, recepciones, movimientos de inventario y auditoría; agregar claves foráneas, restricciones e índices según `data-model.md`; usar `BEGIN`/`COMMIT`, no incluir `DROP`, y conservar `purchase_orders` como ciclo independiente.

## Phase 2: Foundational

**Purpose**: Establecer las reglas compartidas que bloquean las historias de compras.

- [x] T002 [P] Definir tipos, estados y validadores puros en `app/domain/purchases.py`: recepción `REGISTERED → PARTIALLY_RECEIVED → RECEIVED`, cancelación sólo antes de recibir, pago `PENDING → PAID`, PEN, cantidades positivas, y cálculos `Decimal` con dos decimales.
- [x] T003 [P] Definir el puerto de persistencia y tipos de entrada/salida de compras en `app/application/ports.py`, incluyendo operaciones transaccionales para crear compra, registrar recepción idempotente, buscar proveedores y consultar historial; identidad actor siempre como argumento interno derivado de sesión.
- [x] T004 [P] Definir errores de dominio/aplicación para duplicado, recurso inexistente, transición inválida, inventario inconsistente y persistencia no disponible en `app/application/errors.py`, siguiendo el formato estructurado actual y sin propagar detalles SQL.

**Checkpoint**: La migración y las reglas/puertos comunes están definidos antes de implementar las historias.

## Phase 3: User Story 1 - Registrar una compra de proveedor (Priority: P1) 🎯 MVP

**Goal**: ADMIN registra un comprobante con proveedor, conceptos, importes y pago sin cambiar stock.

**Independent Test**: Como ADMIN, registrar un comprobante de dos líneas y verificar en la respuesta que persisten proveedor, documento, fecha, líneas, total, estado de pago y responsable; comprobar que el stock antes/después es igual. Repetir comprobante debe responder conflicto.

### Implementation

- [x] T005 [US1] Implementar validación de compra en `app/domain/purchases.py`: cada línea conserva producto nullable, código/descripción snapshot, cantidad > 0, costo >= 0, descuento/impuesto >= 0; `line_total` y totales usan `NUMERIC(14,2)`/`Decimal`; calcular `total = subtotal - descuento + impuesto + cargos` y rechazar valores inconsistentes.
- [x] T006 [US1] Implementar el caso de uso de registro y consulta por ID en `app/application/purchases.py`: aceptar proveedor activo, orden opcional, documento, fechas, PEN, método/estado pago y líneas; responsable viene del actor; al guardar no alterar existencias ni crear asiento contable.
- [x] T007 [US1] Implementar persistencia de compra y líneas en `app/adapters/persistence/purchases.py` con transacción: snapshots de proveedor/repuesto; vinculación opcional a `purchase_orders`; unicidad de proveedor + tipo + serie normalizada + número; responder conflicto ante duplicado concurrente; conservar snapshots aunque las relaciones se desactiven o queden nulas.
- [x] T008 [US1] Crear modelos HTTP Pydantic y rutas `POST /api/admin/purchases` y `GET /api/admin/purchases/{purchase_id}` en `app/adapters/api/purchases.py`; usar `extra="forbid"`, `require_admin`, actor de sesión, errores 401/403/404/409/422/503 y respuestas conforme a `contracts/purchases.openapi.yaml`.
- [x] T009 [US1] Registrar el router `/api/admin/purchases` en `app/infrastructure/chat_app.py`, inyectar fábrica de repositorio y aplicar `Cache-Control: no-store` a las rutas de compras administrativas.

**Checkpoint**: El alta y detalle mínimo de una compra están disponibles para ADMIN y no modifican el stock.

## Phase 4: User Story 2 - Mantener proveedores disponibles para compras (Priority: P2)

**Goal**: ADMIN consulta, crea, actualiza y desactiva proveedores sin perder historial.

**Independent Test**: Consultar proveedores, crear uno con datos comerciales, seleccionarlo en una compra y desactivarlo; compras anteriores siguen mostrando el snapshot.

### Implementation

- [x] T010 [US2] Implementar reglas de proveedor en `app/domain/purchases.py`: nombre legal requerido, `tax_id` nullable y único cuando se informa, correo/teléfono/dirección opcionales, plazo estimado nullable >= 0 y desactivación lógica.
- [x] T011 [US2] Implementar casos de uso list/create/update de proveedor con filtro activo/búsqueda y paginación en `app/application/purchases.py`; no permitir borrar físicamente un proveedor relacionado con compras.
- [x] T012 [US2] Implementar consultas y escrituras de proveedor en `app/adapters/persistence/purchases.py`, ampliando el `name VARCHAR(150)` existente sin truncar datos; preservar `contact_email`, `phone`, `delivery_lead_days`, `active` y `created_at`.
- [x] T013 [US2] Agregar `GET/POST /api/admin/suppliers` y `PATCH /api/admin/suppliers/{supplier_id}` en `app/adapters/api/purchases.py`, con filtros `active`/`search`, paginación `limit` 1–100 y `offset` >= 0, ADMIN y contrato OpenAPI.

**Checkpoint**: Proveedores se mantienen sin borrar ni cambiar la evidencia histórica de compras.

## Phase 5: User Story 3 - Confirmar recepción de compra (Priority: P2)

**Goal**: ADMIN confirma llegadas físicas, incluso parciales, y el stock aumenta sólo por cantidades recibidas.

**Independent Test**: Registrar compra sin variar stock; confirmar una cantidad parcial y verificar estado/movimiento; repetir la misma clave sin duplicar stock; confirmar saldo restante y verificar estado `RECEIVED`.

### Implementation

- [x] T014 [US3] Implementar validación de recepción en `app/domain/purchases.py`: cantidades recibidas > 0; acumulado por línea nunca supera cantidad facturada; sólo estado `REGISTERED`/`PARTIALLY_RECEIVED`; permitir stock únicamente para cantidades enteras vinculadas al catálogo.
- [x] T015 [US3] Implementar caso de uso de recepción en `app/application/purchases.py`: exigir actor ADMIN e `Idempotency-Key` UUID; derivar recepción parcial/completa según cantidades acumuladas; no recibir compras canceladas/completas ni admitir IDs de repuesto como autoridad sobre líneas.
- [x] T016 [US3] Implementar transacción de recepción en `app/adapters/persistence/purchases.py`: bloquear compra/líneas relevantes; insertar recepción, ítems, movimientos y auditoría; incrementar `spare_parts.current_stock`; revertir todo si cualquier paso falla; replay con mismo actor/compra/clave/payload devuelve evento existente y clave con payload distinto genera conflicto.
- [x] T017 [US3] Agregar `POST /api/admin/purchases/{purchase_id}/receipts` y `GET /api/admin/purchases/{purchase_id}/receipts` en `app/adapters/api/purchases.py`; requerir header `Idempotency-Key` UUID, validar cuerpo y devolver 201 o 200 con `Idempotent-Replayed: true` en replay.
- [x] T018 [US3] Cubrir inventario vinculado nullable y snapshots en respuesta de recepción en `app/adapters/persistence/purchases.py`: conceptos no asociados al catálogo quedan en historial y no producen movimiento; movimientos conservan `code_snapshot` y `name_snapshot`, y `spare_part_id` usa `ON DELETE SET NULL` para preservar evidencia si se elimina el catálogo.

**Checkpoint**: Recepciones confirmadas son atómicas, auditables e idempotentes; registrar la factura sigue sin incrementar stock.

## Phase 6: User Story 4 - Consultar y rastrear compras (Priority: P3)

**Goal**: ADMIN busca compras, revisa detalle e historial y cancela sólo compras sin recepciones.

**Independent Test**: Filtrar por proveedor, rango de fecha y estado; verificar snapshots, líneas, recepciones, pago, responsable e historial; cancelar compra sin recepción y confirmar que una compra recibida no se cancela.

### Implementation

- [x] T019 [US4] Implementar listado paginado y filtros en `app/application/purchases.py`: proveedor, fecha desde/hasta, estado de compra, estado de pago y número de documento; validar que `from_date <= to_date`.
- [x] T020 [US4] Implementar consultas SQL paginadas y detalle completo en `app/adapters/persistence/purchases.py`: devolver cabecera, líneas, snapshots, recibos, movimientos y auditoría sin N+1 ni revelar credenciales/datos ajenos.
- [x] T021 [US4] Implementar cancelación auditada en `app/domain/purchases.py` y `app/application/purchases.py`: permitir sólo compra no recibida, transición a `CANCELLED`, sin borrar físicamente ni modificar inventario.
- [x] T022 [US4] Agregar `GET /api/admin/purchases` con filtros/paginación, `PATCH /api/admin/purchases/{purchase_id}` sólo para campos permitidos y `POST /api/admin/purchases/{purchase_id}/cancel` en `app/adapters/api/purchases.py`; transición de pago sólo `PENDING → PAID`, cada cambio registra actor/fecha.
- [x] T023 [US4] Completar auditoría append-only de cambios permitidos en `app/adapters/persistence/purchases.py`; guardar actor, tipo, campos cambiados y timestamp en la misma transacción que la operación.

**Checkpoint**: Todas las compras y cambios pueden consultarse y atribuirse a ADMIN y una fecha.

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cerrar coherencia documental, seguridad y validación end-to-end.

- [x] T024 [P] Alinear `specs/006-registro-compras-proveedores/contracts/purchases.openapi.yaml` con rutas, schemas, estados, errores, paginación, límites y respuestas efectivamente implementados.
- [x] T025 [P] Actualizar la documentación backend en `README.md`, incluyendo referencia al contrato OpenAPI, orden de aplicación de la migración y advertencia de usar sólo una base autorizada.
- [x] T026 Ejecutar escenarios de `specs/006-registro-compras-proveedores/quickstart.md` en PostgreSQL de prueba y registrar resultado de migración, permisos, duplicados, total, recepción idempotente y ausencia de asientos automáticos.

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: T001 prepara el esquema que usan las demás tareas.
- **Foundational (Phase 2)**: T002–T004 dependen de T001 y bloquean las historias.
- **US1 (Phase 3)**: depende de migración y dominio/puerto; MVP inicial.
- **US2 (Phase 4)**: depende de T001–T004; puede desarrollarse en paralelo con US1 tras foundation, pero el uso de proveedor nuevo en el flujo end-to-end espera US2.
- **US3 (Phase 5)**: requiere compra/líneas de US1 y esquema de movimientos de T001.
- **US4 (Phase 6)**: requiere entidades de US1; consultas de recibos completas requieren US3.
- **Polish (Phase 7)**: después de historias entregadas.

### User Story Dependencies

- **US1 (P1)**: independiente luego de Foundation y datos de proveedor ya existentes; MVP.
- **US2 (P2)**: independiente después de Foundation; integra al registro de US1.
- **US3 (P2)**: depende de compra y líneas de US1 para poder recibirlas.
- **US4 (P3)**: lectura base depende de US1; historial completo depende además de US3.

### Parallel Opportunities

- T002 y T003 pueden avanzar en paralelo después de T001; T004 puede desarrollarse en paralelo con T002/T003 porque modifica `app/application/errors.py`.
- T010 puede avanzar en paralelo con T005 después de Foundation; evitar ediciones simultáneas al mismo módulo en una rama: integrar secuencialmente.
- T014 y T019 son reglas de archivos/módulos distintos sólo si se separan funciones; persistencia API se mantiene secuencial por compartir `purchases.py`.
- T024 y T025 pueden avanzar en paralelo tras estabilizar las rutas.
- Aunque US1 y US2 tienen flujos diferenciados, sus tareas modifican módulos compartidos (`purchases.py`), así que integrar sus cambios en secuencia para evitar conflictos.

## Implementation Strategy

### MVP First (US1)

1. Completar T001–T004.
2. Completar US1 (T005–T009): crear compra y consultar su detalle, conservar snapshots, calcular importes y no tocar stock.
3. Validar el flujo de registro y conflicto de duplicado en base de prueba.
4. Continuar con US2 para alta de proveedores desde la interfaz administrativa; luego US3 para recepción/inventario y US4 para filtros/auditoría/cancelación.

### Notas de ejecución

- No ejecutar `contexto/tablas postgres v2.sql` para actualizar una base existente: contiene instrucciones destructivas de esquema inicial.
- Aplicar `sql/migrations/005_supplier_purchases.sql` sólo a base de prueba autorizada y después de respaldo/verificación de destino.
- Mantener el libro contable independiente; no crear automáticamente `accounting_entries`.
- Las tareas marcadas `[P]` no comparten archivos ni dependen de cambios incompletos; toda tarea de historia usa su etiqueta `[USn]`.
