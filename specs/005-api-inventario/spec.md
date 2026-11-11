# Feature Specification: API de inventario para el taller

**Feature Branch**: `[005-api-inventario]`
**Created**: 2026-11-02
**Status**: Draft
**Input**: User description: "Revisar el inventario que muestra y necesita el frontend y especificar las rutas API del backend para que el frontend las consuma."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar inventario y disponibilidad (Priority: P1)

El personal del taller abre Inventario y necesita ver los repuestos activos con su código, nombre, categoría, compatibilidad o descripción, existencia, mínimo de alerta y precio en PEN. La pantalla calcula búsqueda, filtros, orden, indicadores de stock crítico y paginación a partir de la lista recibida.

**Why this priority**: Sin una lista real, el frontend permanece en modo demostración y no puede presentar ni administrar el catálogo persistido.

**Independent Test**: Con sesión de personal y repuestos en la base de datos, consultar el inventario y verificar que cada campo mostrado coincide con el registro; una sesión de cliente debe ser rechazada.

**Acceptance Scenarios**:

1. **Given** una sesión válida de personal y repuestos activos e inactivos, **When** consulta el inventario, **Then** recibe los activos con los campos requeridos y el precio como importe decimal con dos decimales.
2. **Given** una sesión válida de personal y ningún repuesto activo, **When** consulta el inventario, **Then** recibe una lista vacía con el mismo formato de respuesta.
3. **Given** una sesión de cliente o ninguna sesión, **When** consulta el inventario, **Then** recibe respectivamente 403 o 401 sin datos del catálogo.
4. **Given** categorías existentes en el catálogo, **When** el frontend obtiene las categorías, **Then** recibe sus valores tal como están almacenados, sin traducir, recortar ni sustituir categorías desconocidas.

### User Story 2 - Registrar un repuesto (Priority: P1)

El personal registra un artículo con código SKU, nombre, categoría, descripción/compatibilidad, precio, existencia inicial y mínimo de alerta; el nuevo repuesto queda disponible en el inventario.

**Why this priority**: El frontend ya ofrece un formulario para registrar repuestos y necesita persistir el alta en el backend.

**Independent Test**: Enviar un alta válida, recibir el repuesto creado y verificar que aparece en la consulta del inventario; repetir el código debe producir un conflicto entendible.

**Acceptance Scenarios**:

1. **Given** datos válidos y un código no utilizado, **When** personal registra el repuesto, **Then** el sistema lo guarda activo y devuelve la representación persistida.
2. **Given** un código que ya existe, **When** personal intenta registrarlo, **Then** recibe 409 y el campo de código se identifica como duplicado.
3. **Given** precio, cantidad, categoría o nombre fuera de las reglas, **When** personal envía el alta, **Then** recibe 422 con un error que permita identificar el dato inválido y no se crea ningún registro.

### User Story 3 - Editar un repuesto y ajustar disponibilidad (Priority: P1)

El personal actualiza los datos de un repuesto existente. El código identifica el registro y permanece inmutable durante la edición; el stock y el mínimo se reemplazan por los valores enviados.

**Why this priority**: La interfaz permite actualizar precios, descripción, categoría y existencias desde el formulario existente.

**Independent Test**: Actualizar un repuesto por su código y consultar de nuevo la lista para verificar todos los campos y `updated_at`.

**Acceptance Scenarios**:

1. **Given** un repuesto existente y una sesión de personal, **When** envía una actualización válida, **Then** el registro conserva su identidad, refleja los campos enviados y devuelve la versión persistida.
2. **Given** un código inexistente, **When** intenta actualizarlo, **Then** recibe 404 y no se crea un repuesto nuevo.
3. **Given** una actualización con datos inválidos, **When** la envía, **Then** recibe 422 y el registro conserva íntegramente su estado previo.

### User Story 4 - Retirar un repuesto del inventario (Priority: P2)

El personal retira un repuesto que ya no debe aparecer disponible. Si el repuesto está referido por un presupuesto, el sistema conserva la integridad del historial y explica que no puede eliminarse.

**Why this priority**: El frontend ofrece la acción de eliminar, mientras que los presupuestos deben conservar la referencia histórica al repuesto.

**Independent Test**: Eliminar un artículo no referenciado y confirmar que deja de aparecer; intentar eliminar uno usado en un presupuesto y confirmar 409 sin perder el registro ni su historial.

**Acceptance Scenarios**:

1. **Given** un repuesto existente que no aparece en detalles de presupuestos, **When** personal lo elimina, **Then** recibe 204 y ya no aparece en el inventario activo.
2. **Given** un repuesto referido por uno o más presupuestos, **When** personal lo elimina, **Then** recibe 409, el repuesto y sus referencias permanecen intactos y el frontend puede mostrar el mensaje de artículo en uso.
3. **Given** un código inexistente, **When** personal intenta eliminarlo, **Then** recibe 404.

### Edge Cases

- El catálogo no contiene repuestos activos: la consulta responde correctamente con `parts: []`.
- Dos altas concurrentes usan el mismo código: solo una puede persistir; la otra recibe 409.
- Un precio se envía como número con precisión excesiva, notación inválida, negativo o cero: se rechaza de manera consistente y nunca se redondea silenciosamente.
- Existencias o mínimo son negativos, fraccionarios o exceden 999999: se rechazan.
- Una categoría del esquema no está entre las cinco opciones actualmente codificadas en el frontend: la API la conserva y la expone; no debe ocultar el artículo ni transformarla.
- La sesión vence entre la carga y una operación de escritura: responde 401 y no aplica cambios.
- Una eliminación coincide con la creación de un presupuesto: la integridad referencial impide perder el detalle histórico y la operación responde como conflicto.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST exponer `GET /api/inventory/parts` para devolver los repuestos activos del inventario en un objeto con la propiedad `parts`.
- **FR-002**: Cada repuesto MUST exponer el identificador numérico estable `id` de `spare_parts.id`, además de `code`, `name`, `category`, `description`, `unit_price`, `current_stock`, `minimum_threshold`, `active`, `created_at` y `updated_at`; los importes MUST conservar precisión de dos decimales y serializarse sin pérdida de precisión. `id` permite que otros módulos creen relaciones con inventario; `code` continúa siendo el identificador público para actualizar o retirar un artículo.
- **FR-003**: El sistema MUST exponer `POST /api/inventory/parts` para registrar un repuesto, `PUT /api/inventory/parts/{code}` para reemplazarlo y `DELETE /api/inventory/parts/{code}` para retirarlo, usando el código como identificador público; el código no será modificable al reemplazar el recurso.
- **FR-004**: Las operaciones de escritura MUST validar código de 1 a 50 caracteres con letras mayúsculas, números y guiones; nombre de 3 a 150 caracteres; categoría no vacía de hasta 50 caracteres; stock y mínimo enteros entre 0 y 999999; y precio mayor que cero, con hasta dos decimales y máximo compatible con el importe persistido.
- **FR-005**: Una alta correcta MUST persistir el artículo como activo y responder con la propiedad `part`; una actualización correcta MUST responder con la misma forma y reflejar la fecha de actualización.
- **FR-006**: El sistema MUST responder 409 ante códigos duplicados y ante la eliminación de un repuesto referenciado por detalles de presupuestos; MUST responder 404 ante una actualización o eliminación de un código inexistente y 422 ante datos inválidos.
- **FR-007**: Una eliminación permitida MUST retirar físicamente el artículo solo cuando no existan referencias que deban conservarse. Las referencias históricas de presupuestos MUST permanecer intactas.
- **FR-008**: El sistema MUST autenticar todas las operaciones y permitir su uso solamente a usuarios con rol `ADMIN` o `TECHNICIAN`; usuarios `CUSTOMER` reciben 403 y usuarios sin sesión válida reciben 401.
- **FR-009**: La respuesta de consulta MUST incluir solo artículos activos, ordenados de forma estable por nombre y código; la interfaz seguirá aplicando búsqueda, filtros, orden visual y paginación local.
- **FR-010**: El sistema MUST exponer `GET /api/inventory/categories` para devolver las categorías distintas presentes entre los repuestos activos, sin traducción, permitiendo que la interfaz ofrezca el catálogo real sin perder categorías existentes.
- **FR-011**: Las categorías y descripciones ingresadas MUST conservarse como texto de catálogo; el backend no limitará las categorías a las cinco opciones actualmente estáticas en el frontend.
- **FR-012**: El sistema MUST usar el esquema actual de `spare_parts` y sus restricciones; esta funcionalidad no requiere nuevas tablas ni cambiar los vínculos existentes de `quote_details` o `purchase_order_items`.
- **FR-013**: Los errores MUST usar un cuerpo JSON estable con un código de error legible por máquina y, para errores de validación, el campo afectado cuando sea aplicable.
- **FR-014**: Las operaciones de escritura MUST ser atómicas: cualquier error de validación, unicidad o integridad debe dejar los datos sin cambios parciales.

### Key Entities

- **Repuesto**: artículo persistido con código único, nombre, categoría libre, descripción/compatibilidad, precio unitario, existencia, mínimo de alerta y fechas de creación/actualización.
- **Categoría de inventario**: valor textual utilizado por los repuestos activos; los valores existentes representan el catálogo real y no deben normalizarse de forma destructiva.
- **Detalle de presupuesto**: referencia histórica a un repuesto cotizado; restringe su eliminación para preservar el detalle del presupuesto.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El personal autenticado puede cargar el inventario completo en una sola consulta y la respuesta contiene todos los campos que la pantalla presenta.
- **SC-002**: El 100% de los repuestos activos con categoría fuera de las cinco opciones actuales se conserva y aparece en la respuesta del inventario y en la lista de categorías.
- **SC-003**: Un usuario sin permisos no obtiene datos ni puede cambiar el inventario: las solicitudes correspondientes finalizan con 401 o 403.
- **SC-004**: Los flujos de alta, edición y eliminación permitida reflejan los cambios al volver a consultar el inventario; los intentos inválidos o en conflicto no alteran los datos.
- **SC-005**: Los precios mostrados conservan exactamente el importe de dos decimales persistido, sin errores de conversión a unidades menores.

## Assumptions

- El frontend seguirá usando sus rutas esperadas: colección de partes para consultar y crear, y recurso identificado por `code` para actualizar o eliminar.
- El precio de venta se maneja en PEN y el frontend representa internamente el dinero en céntimos; la API devuelve y recibe el valor decimal con dos posiciones como texto JSON.
- Los roles actuales `ADMIN` y `TECHNICIAN` representan al personal del taller; `CUSTOMER` no administra inventario.
- El inventario de la interfaz carga la lista completa y aplica localmente filtros de texto, categoría, stock crítico, orden y páginas de cuatro elementos; no se requiere paginación ni búsqueda en servidor en esta versión.
- La acción denominada “Eliminar” en la interfaz es física cuando no hay dependencias. Cuando hay detalles de presupuestos, se rechaza con 409 para respetar el contrato actual del frontend y preservar la trazabilidad financiera.
- La interfaz actual presenta cinco categorías fijas y puede no permitir seleccionar categorías ya presentes en el inventario. La API conservará el catálogo completo y entregará sus categorías; consumirlas dinámicamente requiere una adaptación posterior del frontend.
- Se reutilizan autenticación por sesión existente, repositorio PostgreSQL y el esquema ampliado indicado por el proyecto; no se crea un movimiento de inventario ni una bitácora de ajustes en esta especificación.
- No se incluyen órdenes de compra, gestión de proveedores ni reserva/descuento de stock por cotización.
