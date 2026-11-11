# Feature Specification: Trazabilidad de movimientos de inventario

**Feature Branch**: `[008-trazabilidad-movimientos-inventario]`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User request: "P0 — Hacer que toda variación de stock deje movimiento. Especificar esta mejora para el backend antes de implementarla."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar aperturas y ajustes de existencias (Priority: P0)

El personal autorizado necesita registrar el stock inicial y corregir el conteo físico de un repuesto. Cada cambio debe quedar asociado a quién lo registró, cuándo ocurrió, qué cantidad varió, cuáles eran las existencias antes y después, y el motivo. El sistema calcula la diferencia a partir del conteo físico informado.

**Why this priority**: El alta y la edición actuales pueden cambiar existencias sin dejar una evidencia de movimiento. Esa brecha impide auditar el inventario.

**Independent Test**: Crear un artículo con existencias en cero, registrar una apertura y después un ajuste físico. En cada operación se consulta el artículo y su historial; ambos deben mostrar saldos coherentes y un movimiento con actor, fecha y motivo.

**Acceptance Scenarios**:

1. **Given** un artículo nuevo y personal autorizado, **When** lo registra, **Then** inicia con stock cero; cualquier saldo inicial debe registrarse por la operación de apertura y genera su movimiento.
2. **Given** un artículo existente, **When** personal informa un conteo físico mayor que el saldo actual y un motivo, **Then** el sistema calcula la diferencia positiva y guarda el nuevo saldo junto con un movimiento de entrada.
3. **Given** un artículo existente, **When** personal informa un conteo físico menor que el saldo actual y un motivo, **Then** el sistema calcula la diferencia negativa y guarda el nuevo saldo junto con un movimiento de salida.
4. **Given** el conteo informado coincide con el saldo actual, **When** personal solicita el ajuste, **Then** el sistema informa que no hubo variación y no crea un movimiento ficticio.
5. **Given** una sesión de cliente o una solicitud sin sesión válida, **When** intenta abrir o ajustar existencias, **Then** la operación se rechaza sin revelar ni alterar datos de inventario.

---

### User Story 2 - Conservar trazabilidad en compras y ventas (Priority: P0)

El personal necesita que la recepción de compras y la salida confirmada por ventas continúen actualizando existencias con un movimiento asociado a su documento de origen. Estas operaciones deben compartir la misma regla de atomicidad que las aperturas y los ajustes.

**Why this priority**: Compras recibidas y ventas confirmadas ya registran movimientos; el cambio debe conservar esos flujos y evitar duplicados o inconsistencias al completar la trazabilidad general.

**Independent Test**: Completar una recepción de compra y una venta confirmada. Verificar que cada cambio de saldo tiene un único movimiento asociado al detalle de su operación y que los saldos y cantidades concuerdan.

**Acceptance Scenarios**:

1. **Given** una recepción válida, **When** se confirma la recepción, **Then** aumentan las existencias y se conserva un único movimiento vinculado a la línea recibida.
2. **Given** una venta aceptada con reserva válida, **When** se confirma la operación que consume las unidades, **Then** disminuyen las existencias y se conserva un único movimiento vinculado a la línea vendida.
3. **Given** un error al guardar el movimiento o actualizar el saldo, **When** la operación termina, **Then** no queda persistido solo uno de esos cambios.
4. **Given** un reintento de una operación ya registrada, **When** se repite con la misma clave de idempotencia, **Then** no vuelve a variar el saldo ni duplica el movimiento.

---

### User Story 3 - Consultar historial auditable por repuesto (Priority: P1)

El personal autorizado necesita revisar los movimientos de un artículo en orden cronológico, con el tipo y motivo, el origen cuando corresponda, la variación, el saldo anterior y posterior, la fecha y el usuario responsable. Las referencias del historial deben conservarse aunque el artículo deje de estar activo.

**Why this priority**: Registrar movimientos sin poder consultarlos no permite responder quién cambió el stock ni explicar el saldo actual.

**Independent Test**: Registrar apertura, ajuste, recepción y salida; consultar el historial por artículo y comprobar que cada movimiento se muestra una vez, en orden estable y con los datos de auditoría esperados.

**Acceptance Scenarios**:

1. **Given** movimientos de distintos tipos para un artículo, **When** personal autorizado consulta su historial, **Then** recibe todos los movimientos visibles en orden cronológico estable con sus saldos y responsables.
2. **Given** filtros de período o tipo y más resultados que el tamaño de página, **When** se consulta el historial, **Then** solo aparecen los resultados coincidentes y la paginación no repite ni omite movimientos.
3. **Given** un usuario cliente o anónimo, **When** consulta el historial, **Then** recibe 403 o 401 respectivamente y no obtiene datos financieros u operativos internos.
4. **Given** un movimiento ya registrado, **When** alguien intenta editarlo o eliminarlo, **Then** el sistema conserva el original; una corrección requiere un nuevo movimiento que lo compense y documente el motivo.

---

### User Story 4 - Establecer un punto de corte para el stock existente (Priority: P1)

Al activar la trazabilidad completa, la organización necesita mantener los movimientos históricos disponibles y establecer el saldo inicial verificable desde el que se controlarán los cambios futuros. Los registros antiguos sin origen confiable no deben convertirse en eventos inventados.

**Why this priority**: El historial actual contiene movimientos de compras y ventas, pero no necesariamente explica todo el saldo acumulado antes de habilitar aperturas y ajustes.

**Independent Test**: Aplicar la migración sobre una copia con artículos con saldo cero y positivo, además de movimientos previos. Verificar que conserva los registros existentes, establece el saldo de corte y no presenta los eventos previos como si fueran movimientos de apertura actuales.

**Acceptance Scenarios**:

1. **Given** artículos y movimientos existentes, **When** se habilita la nueva trazabilidad, **Then** se conservan identificadores, datos y vínculos anteriores, y cada saldo vigente queda asociado a un punto de corte explícito.
2. **Given** movimientos previos a la fecha de corte, **When** se consulta el historial, **Then** se identifican como historia anterior al corte y no se suman nuevamente al saldo inicial posterior al corte.
3. **Given** una migración que se reintenta, **When** vuelve a aplicarse, **Then** no duplica saldos iniciales ni altera los movimientos existentes.

### Edge Cases

- Un conteo físico es negativo, fraccionario, excede el máximo permitido o carece de motivo: se rechaza y no cambia el saldo.
- El conteo físico propuesto dejaría menos unidades que las reservadas para cotizaciones aceptadas: se rechaza sin cambiar saldo ni reservas.
- Dos ajustes concurrentes afectan el mismo artículo: ambos se procesan sobre saldos serializados; ninguno sobrescribe silenciosamente el resultado del otro.
- La sesión expira antes de confirmar una apertura o ajuste: no se guarda saldo ni movimiento.
- Se repite una solicitud por timeout: una clave de idempotencia evita aplicar la misma variación más de una vez.
- Un artículo con movimientos se intenta eliminar: el sistema conserva la trazabilidad y rechaza la eliminación física; el artículo puede retirarse del catálogo sin borrar su historial.
- Un movimiento queda inválido por tipo, signo, origen, saldo o actor: se rechaza íntegramente.
- La diferencia de ajuste es cero: se devuelve un resultado sin variación y no se crea un movimiento con delta cero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Toda operación que cambie el stock de un repuesto MUST registrar exactamente un movimiento de inventario en la misma operación confirmada. Si falla la actualización del saldo o el registro del movimiento, MUST conservarse el estado previo completo.
- **FR-002**: La creación ordinaria de un repuesto MUST dejar las existencias en cero. Un saldo inicial distinto de cero MUST registrarse mediante una apertura de stock con motivo y responsable autenticado.
- **FR-003**: La edición ordinaria del catálogo MUST permitir actualizar los datos descriptivos, precio y umbral de alerta, pero MUST NOT cambiar directamente el saldo de stock.
- **FR-004**: Una apertura o ajuste manual MUST recibir el conteo físico actual y un motivo no vacío. El sistema MUST calcular el delta y el saldo final desde el saldo persistido, sin aceptar del solicitante saldos anterior/final o un delta que sustituyan ese cálculo.
- **FR-005**: Los movimientos MUST distinguir aperturas, ajustes de entrada, ajustes de salida, recepciones de compra y ventas confirmadas; cada movimiento MUST conservar el tipo, la cantidad, el saldo anterior y posterior, la fecha, el actor y las instantáneas de código y nombre del artículo.
- **FR-006**: El motivo es obligatorio para aperturas y ajustes manuales. El origen de recepción o venta MUST vincularse a su línea de documento correspondiente. El actor MUST derivarse de la sesión autenticada y MUST NOT aceptarse desde datos editables enviados por quien realiza la solicitud.
- **FR-007**: La creación de aperturas y ajustes MUST estar disponible únicamente para `ADMIN` y `TECHNICIAN` autenticados. Solicitudes anónimas reciben 401 y cuentas `CUSTOMER` reciben 403. Se conserva el mecanismo de sesión vigente.
- **FR-008**: Ningún movimiento puede llevar el stock a un valor negativo ni reducirlo por debajo de las unidades reservadas. Un conflicto con stock reservado MUST rechazarse sin alterar existencias ni reservas.
- **FR-009**: Variaciones concurrentes sobre el mismo artículo MUST basarse en el saldo vigente al confirmar cada operación; no se permiten actualizaciones perdidas ni saldos derivados de una lectura obsoleta.
- **FR-010**: Reintentar la misma operación confirmada con la misma clave de idempotencia MUST devolver el resultado ya registrado sin aplicar otra variación. Una nueva operación distinta puede registrar un nuevo movimiento.
- **FR-011**: El historial MUST permitir consultar movimientos por artículo, filtrar por período y tipo, y recorrer resultados con paginación estable. Cada resultado MUST incluir movimiento, variación, saldo anterior/posterior, actor, fecha, motivo y origen cuando existan.
- **FR-012**: Los movimientos registrados MUST ser inmutables. Una corrección se registra como un nuevo movimiento compensatorio con actor, fecha y motivo; nunca se borra o reescribe el movimiento original.
- **FR-013**: La recepción de compras y el consumo de stock por ventas MUST seguir produciendo exactamente un movimiento por línea que cambie stock, conservando sus relaciones de origen y las políticas actuales de reserva.
- **FR-014**: La migración MUST conservar los movimientos y relaciones preexistentes, definir un punto de corte para cada saldo vigente y distinguir la historia anterior al corte de los movimientos nuevos. MUST NOT fabricar recibos, ventas ni ajustes históricos sin evidencia.
- **FR-015**: La actualización del esquema MUST ser versionada, repetible sin duplicar saldos iniciales ni movimientos, y compatible con las existencias y reservas ya persistidas. Las reglas de tipo, signo, origen, saldo no negativo y auditoría MUST validarse incluso cuando una operación no provenga del flujo de interfaz.
- **FR-016**: Un artículo con movimientos MUST conservar su historial al ser retirado. La eliminación física de artículos con movimientos debe rechazarse; el retiro del catálogo no elimina movimientos ni instantáneas.
- **FR-017**: Los errores de validación, autorización, conflicto de reserva, recurso inexistente e indisponibilidad MUST tener respuestas estables que no revelen consultas, credenciales ni detalles internos de base de datos.
- **FR-018**: Los contratos del backend MUST documentar las operaciones para apertura, ajuste e historial, incluidas sus entradas, resultados, permisos y errores; los cambios se limitan al backend.
- **FR-019**: Durante la transición, el backend MUST seguir aceptando `current_stock` opcional desde clientes frontend existentes. Si se envía al crear o editar un repuesto, MUST traducirse dentro de la transacción a una apertura/ajuste con el actor autenticado y un motivo de compatibilidad; el campo se marca obsoleto en OpenAPI y no debe permitir una actualización directa de saldo.

### Estado actual y alcance del cambio

- **Existe**: el catálogo permite crear y editar `current_stock` directamente; las recepciones de compras y ventas confirmadas ya generan movimientos asociados a sus líneas; `inventory_movements` conserva cantidad, saldos anterior/posterior, actor, fecha e instantáneas del artículo.
- **Debe modificarse**: las operaciones ordinarias del catálogo dejan de alterar stock directamente; como compatibilidad temporal, `current_stock` se traduce en un movimiento auditable; las reglas de movimientos y su esquema admiten aperturas y ajustes manuales; la eliminación física se reemplaza por retiro cuando existe historial; los flujos de compra y venta mantienen atomicidad.
- **Debe agregarse**: operaciones autenticadas para apertura, conteo/ajuste y consulta del historial; auditoría con motivo y control de idempotencia; migración que establece el corte sin atribuir falsamente orígenes históricos.
- **Fuera de alcance**: cambios en el frontend, gestión de proveedores, rediseño de ventas o reservas, importación de movimientos históricos sin evidencia y ejecución de la migración durante Specify.

### Key Entities *(include if feature involves data)*

- **Movimiento de inventario**: evidencia inmutable de una variación, con tipo, delta, saldos anterior/posterior, actor, fecha, motivo, instantáneas del artículo y origen aplicable.
- **Saldo de artículo**: cantidad vigente de un repuesto; los ajustes manuales se derivan de un conteo físico y no de saldos calculados por quien llama al servicio.
- **Punto de corte de trazabilidad**: saldo vigente tomado como base al comenzar el registro completo, separado de eventos antiguos cuyo origen no puede reconstruirse con fiabilidad.
- **Origen de movimiento**: línea de recepción, línea de venta, apertura o ajuste manual que explica por qué cambió el saldo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las operaciones confirmadas que cambian existencias crea exactamente un movimiento con el mismo delta y saldo final.
- **SC-002**: El 100% de aperturas y ajustes exitosos identifica al actor autenticado, la fecha y el motivo; ninguna solicitud puede atribuirlos a otra cuenta mediante campos editables.
- **SC-003**: El 100% de fallos durante una variación conserva tanto el saldo como el historial previo, sin escrituras parciales.
- **SC-004**: Un reintento con igual clave de idempotencia no crea un segundo movimiento ni vuelve a cambiar el saldo.
- **SC-005**: Personal autorizado puede reconstruir el saldo desde el punto de corte y sus movimientos posteriores; las reservas y los movimientos anteriores se conservan sin duplicación.
- **SC-006**: Las cuentas sin sesión o con rol de cliente no pueden realizar ni consultar operaciones internas de movimientos.

## Assumptions

- Los roles `ADMIN` y `TECHNICIAN` conservan los permisos de personal que ya tienen para gestionar el inventario; las cuentas `CUSTOMER` no acceden al historial interno.
- El alta de un artículo comienza en cero. Un conteo inicial positivo se registra como apertura separada, con el mismo actor y motivo requeridos para un ajuste.
- Para no romper inmediatamente el frontend ya desplegado, `current_stock` se conserva opcional y obsoleto durante la transición. Un cambio de frontend posterior podrá omitirlo y usar las rutas explícitas de apertura/ajuste.
- El punto de corte crea una base auditable para movimientos futuros; los movimientos antiguos se conservan pero no se reinterpretan ni se vuelven a sumar al saldo de corte.
- Un conteo que queda por debajo de unidades reservadas no libera reservas automáticamente; requiere resolver el conflicto antes de ajustar.
- El frontend no se modifica en esta fase; el contrato backend queda especificado para una integración posterior.
- La especificación no ejecuta migraciones ni implementa rutas o cambios de base de datos.
