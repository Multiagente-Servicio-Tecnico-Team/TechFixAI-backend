# Tasks: API de inventario

**Input**: Design documents from specs/005-api-inventario/

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/inventory.openapi.yaml, quickstart.md

**Organization**: Tasks are grouped by user story to allow incremental implementation.

## Phase 1: Setup

**Purpose**: Preparar los módulos de inventario dentro de la arquitectura existente. No se agregan dependencias ni migraciones.

- [X] T001 Crear los módulos de feature app/domain/inventory.py, app/application/inventory.py, app/adapters/persistence/inventory.py y app/adapters/api/inventory.py respetando las convenciones existentes de paquetes.

## Phase 2: Foundational

**Purpose**: Definir contratos y autorización compartidos que bloquean todas las historias.

- [X] T002 [P] Añadir InventoryRepository Protocol en app/application/ports.py con operaciones list_parts, list_categories, create_part, update_part y delete_part.
- [X] T003 [P] Añadir errores de inventario de validación, conflicto, no encontrado y persistencia en app/application/errors.py con códigos estables de la especificación.
- [X] T004 Implementar require_staff en app/accounts/session.py para aceptar ADMIN y TECHNICIAN, rechazar CUSTOMER con 403 y conservar el 401 de sesión inválida; no cambiar require_admin ni require_customer.

**Checkpoint**: los módulos, el puerto, errores y guard de personal están definidos antes de implementar casos de uso.

## Phase 3: User Story 1 - Consultar inventario y disponibilidad (Priority: P1) 🎯 MVP

**Goal**: El personal consulta la lista completa de repuestos activos y sus categorías para alimentar la pantalla de inventario.

**Independent Test**: Con sesión de personal, GET /api/inventory/parts devuelve {parts: [...]} con campos consumibles y GET /api/inventory/categories devuelve categorías exactas. CUSTOMER obtiene 403; sin sesión se obtiene 401.

### Tests for User Story 1

- [X] T005 [P] [US1] Añadir pruebas de contrato para GET /api/inventory/parts y GET /api/inventory/categories en tests/contract/test_inventory_contract.py, incluyendo forma de respuesta, campos, cookie y códigos 401/403.
- [X] T006 [P] [US1] Añadir pruebas de integración de lectura, categorías vacías, filtro active y autorización ADMIN/TECHNICIAN/CUSTOMER en tests/integration/test_inventory_api.py.

### Implementation for User Story 1

- [X] T007 [P] [US1] Definir la proyección InventoryPart y serialización exacta de Decimal y timestamps en app/domain/inventory.py, exponiendo el id numérico estable además de code, name, category, description, unit_price, current_stock, minimum_threshold, active, created_at y updated_at.
- [X] T008 [P] [US1] Implementar list_parts y list_categories en app/adapters/persistence/inventory.py: filtrar active IS TRUE, ordenar partes por name y code, omitir categorías NULL/vacías y devolver categorías distintas sin traducir.
- [X] T009 [US1] Implementar InventoryService.list_parts y list_categories en app/application/inventory.py usando el puerto InventoryRepository y los errores tipados.
- [X] T010 [US1] Implementar GET /api/inventory/parts y GET /api/inventory/categories en app/adapters/api/inventory.py; devolver {parts: [...]} y {categories: [...]}, restringir con require_staff y ajustar 401/403/503 al contrato.
- [X] T011 Integrar create_inventory_router en app/infrastructure/chat_app.py con el guard de personal y el adaptador PostgreSQL; mantener lista completa para que filtros, orden y paginación sigan en el frontend.

**Checkpoint**: listado y categorías reales funcionan de forma independiente, y el frontend puede salir del modo demo para consultar.

## Phase 4: User Story 2 - Registrar un repuesto (Priority: P1)

**Goal**: El personal crea un repuesto activo desde el formulario existente.

**Independent Test**: Un alta válida devuelve 201 y {part: ...}; al consultar aparece una vez. Un código duplicado produce 409 y una entrada inválida produce 422 sin persistencia parcial.

### Tests for User Story 2

- [X] T012 [P] [US2] Añadir casos de contrato POST para respuesta 201, duplicado 409, validación 422 y cuerpo de error en tests/contract/test_inventory_contract.py.
- [X] T013 [P] [US2] Añadir pruebas de integración para alta activa, visibilidad en listado, carrera/código duplicado y rechazo de payload inválido en tests/integration/test_inventory_api.py.

### Implementation for User Story 2

- [X] T014 [P] [US2] Implementar en app/domain/inventory.py la validación de alta: code de 1–50 caracteres con letras mayúsculas, dígitos y guiones; name de 3–150; category no vacía de hasta 50; current_stock y minimum_threshold enteros de 0 a 999999; unit_price positivo con hasta dos decimales y dentro de NUMERIC(10,2); description opcional.
- [X] T015 [P] [US2] Implementar create_part en app/adapters/persistence/inventory.py con SQL parametrizado y transacción; establecer active=true, usar Decimal y convertir violación de unicidad de code a InventoryConflict sin exponer detalles SQL.
- [X] T016 [US2] Implementar InventoryService.create_part en app/application/inventory.py para validar el command del dominio y persistirlo a través de InventoryRepository.
- [X] T017 [US2] Implementar POST /api/inventory/parts en app/adapters/api/inventory.py; rechazar campos no definidos, responder 201 con {part: ...}, y mapear duplicados a 409 e inválidos a 422 con código y campo aplicables.

**Checkpoint**: el alta del formulario se persiste y la respuesta corresponde al artículo almacenado.

## Phase 5: User Story 3 - Editar repuesto y ajustar disponibilidad (Priority: P1)

**Goal**: El personal reemplaza los datos editables y ajusta existencias sin cambiar el SKU.

**Independent Test**: PUT de un artículo existente devuelve 200 con los nuevos valores y updated_at actualizado; un código desconocido devuelve 404 y datos inválidos no cambian el registro.

### Tests for User Story 3

- [X] T018 [P] [US3] Añadir casos de contrato PUT para reemplazo, código de ruta inmutable, 404 y 422 en tests/contract/test_inventory_contract.py.
- [X] T019 [P] [US3] Añadir pruebas de integración de actualización, updated_at, atomicidad y preflight CORS PUT con credenciales en tests/integration/test_inventory_api.py.

### Implementation for User Story 3

- [X] T020 [P] [US3] Añadir validación de reemplazo en app/domain/inventory.py reutilizando las reglas de alta y exigiendo que el code del cuerpo coincida exactamente con el code de ruta.
- [X] T021 [P] [US3] Implementar update_part en app/adapters/persistence/inventory.py para actualizar únicamente name, category, description, unit_price, current_stock y minimum_threshold por code, dejando que el trigger actualice updated_at y devolviendo no encontrado cuando no haya fila.
- [X] T022 [US3] Implementar InventoryService.update_part en app/application/inventory.py; convertir recurso inexistente a InventoryNotFound y mantener atomicidad frente a validaciones y conflictos.
- [X] T023 [US3] Implementar PUT /api/inventory/parts/{code} en app/adapters/api/inventory.py con respuesta 200 {part}; agregar PUT a allow_methods de CORS en app/infrastructure/chat_app.py sin retirar los métodos actuales.

**Checkpoint**: el navegador puede actualizar artículos con cookie de sesión y el preflight CORS acepta PUT.

## Phase 6: User Story 4 - Retirar un repuesto del inventario (Priority: P2)

**Goal**: El personal elimina repuestos no referenciados y conserva los que forman parte de presupuestos.

**Independent Test**: DELETE de artículo sin dependencias devuelve 204; DELETE de artículo con quote_details devuelve 409/in_use y conserva artículo e historial; SKU inexistente devuelve 404.

### Tests for User Story 4

- [X] T024 [P] [US4] Añadir casos de contrato DELETE para 204 sin cuerpo, 404 y 409/in_use en tests/contract/test_inventory_contract.py.
- [X] T025 [P] [US4] Añadir pruebas de integración con FK real: borrar repuesto sin citas, conservar repuesto con quote_details y respetar ON DELETE SET NULL de purchase_order_items en tests/integration/test_inventory_api.py.

### Implementation for User Story 4

- [X] T026 [P] [US4] Implementar delete_part en app/adapters/persistence/inventory.py dentro de una transacción; localizar por code, borrar solo el repuesto y mapear de forma acotada IntegrityError de quote_details a InventoryConflict(in_use), permitiendo el ON DELETE SET NULL definido para purchase_order_items.
- [X] T027 [US4] Implementar InventoryService.delete_part en app/application/inventory.py para propagar InventoryNotFound e InventoryConflict sin filtrar excepciones técnicas.
- [X] T028 [US4] Implementar DELETE /api/inventory/parts/{code} en app/adapters/api/inventory.py; responder 204 sin cuerpo, 404 si falta el código y 409 con code in_use para una dependencia de presupuesto.

**Checkpoint**: la acción de eliminación del frontend respeta la integridad de presupuestos y comunica el conflicto existente.

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Mantener la documentación y el contrato alineados con el comportamiento implementado.

- [X] T029 [P] Actualizar features.md y docs.md con la API de inventario, sus rutas, autorización, esquema reutilizado y pruebas/documentación asociadas.
- [X] T030 Registrar en memory.md el alcance realmente implementado, decisiones de categorías y eliminación, migraciones (ninguna) y limitaciones de integración frontend.

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): independiente; crea módulos de feature.
- Foundational (Phase 2): depende de Setup y bloquea las historias.
- US1 (Phase 3): depende de Foundational; es el MVP de consulta real.
- US2 (Phase 4) y US3 (Phase 5): dependen de los contratos y el router establecidos por US1. Se recomienda hacerlas en ese orden por ser operaciones distintas sobre el mismo recurso.
- US4 (Phase 6): depende del adaptador y serialización del recurso de US1; puede desarrollarse después de US2/US3.
- Polish (Phase 7): depende de completar las historias que se vayan a entregar.

### User Story Dependencies

- US1 (P1): depende únicamente de Foundational.
- US2 (P1): necesita el router, guard, recurso y puerto de US1.
- US3 (P1): necesita el router, guard, recurso y puerto de US1.
- US4 (P2): necesita el recurso, guard y puerto de US1.

### Parallel Opportunities

- T002, T003 y T004 trabajan archivos distintos y pueden ejecutarse en paralelo después de T001.
- En US1, T005/T006 (contrato e integración) pueden avanzar juntos; luego T007/T008 pueden avanzar en paralelo. T009 integra la aplicación, T010 implementa las rutas y T011 las registra.
- En US2, T012/T013 (contrato e integración) pueden avanzar juntos; después T014/T015 (dominio y persistencia) pueden avanzar en paralelo. T016 integra ambos y T017 publica POST.
- En US3, T018/T019 (contrato e integración) pueden avanzar juntos; después T020/T021 (dominio y persistencia) pueden avanzar en paralelo. T022 integra ambos y T023 publica PUT y corrige CORS.
- En US4, T024/T025 (contrato e integración) pueden avanzar juntos; T026 implementa persistencia, T027 el caso de uso y T028 la ruta.
- T029 y T030 pueden ejecutarse en paralelo porque actualizan documentos distintos.
- No se recomienda paralelizar historias sobre app/infrastructure/chat_app.py o app/adapters/api/inventory.py para evitar conflictos de integración.

## Implementation Strategy

### MVP First (US1)

1. Completar Setup y Foundational.
2. Completar US1 para que la pantalla consulte catálogo y categorías del backend.
3. Validar US1 de forma independiente con los escenarios de spec.md/quickstart.md.
4. Continuar con alta, edición y eliminación por separado.

### Incremental Delivery

1. Setup + Foundational.
2. US1: lectura del inventario y categorías.
3. US2: alta.
4. US3: edición y CORS PUT.
5. US4: eliminación segura por FK.
6. Actualizar documentación según lo que se implemente realmente.

## Notes

- No se incluyen tareas para crear migración o dependencias: el modelo requerido ya existe.
- El cliente frontend ya usa paths y respuestas documentados; el endpoint de categorías necesita una conexión posterior en el frontend para sustituir opciones estáticas.
- Las pruebas de cada historia deben implementarse primero y fallar antes de su implementación; no se ejecutan como parte de esta generación de tareas.
