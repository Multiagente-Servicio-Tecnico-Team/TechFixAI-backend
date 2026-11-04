# Feature Specification: Gestión de clientes comerciales

**Feature Branch**: `007-gestion-clientes-comerciales`

**Created**: 2026-11-03

**Status**: Draft — decisiones de negocio resueltas; listo para planificación

**Input**: User description: Separar cuentas autenticadas (`users`) de clientes comerciales (`customers`) y actualizar los vínculos de tickets, cotizaciones y pagos en el backend, con migración que conserve los registros existentes. Este feature es nuevo y complementa `004-gestion-admin-tickets`; no reemplaza ni modifica ese spec.

## User Scenarios & Testing

### User Story 1 — Registrar clientes con o sin cuenta del portal (Priority: P1)

El personal puede registrar a una persona o empresa como cliente comercial aunque no tenga credenciales. Una cuenta del portal puede vincularse a un único perfil de cliente, sin mezclar datos de acceso con los datos comerciales ni crear cuentas ficticias.

**Why this priority**: Los tickets y las cotizaciones manuales necesitan identificar a quién se atiende aunque no exista una cuenta de portal.

**Independent Test**: Crear un cliente manual sin usuario, crear otro perfil vinculado a una cuenta existente y comprobar que cada uno puede utilizarse en los flujos autorizados.

**Acceptance Scenarios**:

1. **Given** un ADMIN autenticado, **When** registra nombre y teléfono de un cliente manual y un correo opcional, **Then** se crea un perfil comercial sin credenciales y queda registrado el ADMIN autor.
2. **Given** una cuenta CUSTOMER activa sin perfil comercial, **When** el backend prepara su acceso a tickets o cotizaciones, **Then** la cuenta se vincula a un perfil comercial y la identidad se resuelve desde la sesión firmada.
3. **Given** un perfil ya vinculado a una cuenta, **When** se intenta asociar esa misma cuenta a otro perfil, **Then** el sistema rechaza la operación sin cambiar los vínculos existentes.
4. **Given** dos clientes con el mismo correo o teléfono, **When** se guardan sus perfiles, **Then** el sistema no los fusiona automáticamente.

### User Story 2 — Gestionar tickets de servicio con cotización opcional (Priority: P1)

El personal gestiona tickets que representan trabajo de servicio técnico. Puede crear un ticket manual para un cliente con o sin cuenta, mientras que el cliente autenticado puede crear o consultar sus propios tickets. El ticket puede permanecer sin cotización o tener cotizaciones de diagnóstico, mano de obra y repuestos.

**Why this priority**: Mantiene la trazabilidad del banco de reparaciones y permite registrar el costo solo cuando el caso realmente requiere una oferta.

**Independent Test**: Crear un ticket de servicio manual sin cotización, crear otro con cotización y comprobar que ambos conservan el mismo cliente y autoría correcta.

**Acceptance Scenarios**:

1. **Given** un cliente manual, **When** un ADMIN crea un ticket de servicio seleccionando su perfil, **Then** el ticket se vincula al cliente y registra el origen y al ADMIN responsable.
2. **Given** un ticket de servicio sin cotización, **When** el ADMIN consulta el detalle, **Then** recibe el ticket y una lista de cotizaciones vacía.
3. **Given** un ticket de servicio y un perfil de cliente, **When** el ADMIN crea una cotización de servicio, **Then** la cotización queda relacionada al ticket y cliente sin alterar los datos históricos del ticket.
4. **Given** un cliente autenticado que crea un ticket desde el portal, **When** envía la solicitud, **Then** el backend usa el perfil vinculado a la sesión y no acepta una identidad de cliente enviada en el cuerpo.
5. **Given** un ticket asociado a un cliente, **When** otro cliente consulta su portal, **Then** no puede ver ni modificar ese ticket o sus cotizaciones.

### User Story 3 — Crear cotizaciones de venta sin ticket de reparación (Priority: P1)

Un ADMIN puede preparar una cotización comercial para productos del inventario, asociada a un cliente del portal o a un cliente manual. El flujo de venta por chat también puede presentar una cotización independiente del ticket de servicio. El cliente puede revisar y aceptar únicamente sus cotizaciones.

**Why this priority**: Una consulta de compra debe quedar en el flujo comercial sin contaminar el tablero del taller.

**Independent Test**: Crear una cotización de venta para un cliente sin cuenta y otra para un cliente del portal; comprobar que ambas aparecen en la gestión comercial y ninguna crea un ticket de servicio.

**Acceptance Scenarios**:

1. **Given** un perfil manual y productos vigentes, **When** el ADMIN registra una cotización de venta, **Then** la cotización queda asociada al cliente y no requiere ni crea un ticket.
2. **Given** un cliente del portal solicita productos por chat, **When** el sistema presenta una oferta, **Then** persiste una cotización de venta pendiente asociada al perfil resuelto desde la sesión, sin crear un ticket de reparación.
3. **Given** una cotización de venta creada para un cliente del portal, **When** ese cliente consulta sus cotizaciones, **Then** ve sus datos, artículos, cantidades, precios, total y estado.
4. **Given** que el cliente acepta una oferta, **When** se registra esa aceptación, **Then** el estado de oferta refleja la aceptación y cualquier pago asociado permanece pendiente hasta que exista confirmación.
5. **Given** un cliente manual sin cuenta, **When** acepta una cotización presencialmente y el ADMIN registra la aceptación explícita, **Then** se conserva el actor y momento de registro sin crear una cuenta para el cliente.
6. **Given** una cotización rechazada, vencida o cancelada, **When** se consulta el historial, **Then** se conserva la cotización y el motivo/actor de cambio si fue registrado.
7. **Given** una cotización de venta pendiente con existencias suficientes, **When** el cliente o un ADMIN registra su aceptación explícita, **Then** el sistema reserva esas cantidades de forma atómica y el pago permanece pendiente.
8. **Given** una cotización de venta sin existencias suficientes al aceptarse, **When** se intenta aceptarla, **Then** el sistema rechaza la aceptación sin crear una reserva parcial ni marcarla aceptada.
9. **Given** una reserva asociada a una cotización que se rechaza, cancela o vence sin pago confirmado, **When** se actualiza ese estado, **Then** se libera la reserva y se conserva el evento de auditoría.

### User Story 4 — Confirmar pagos y registrar la venta con trazabilidad (Priority: P1)

El personal puede registrar la confirmación de un pago vinculado a una cotización aceptada. Solo después de una confirmación válida se registra la venta, conservando la relación con el cliente, la oferta y sus artículos. El estado pagado corresponde al pago o a la venta, no al estado de la oferta.

**Why this priority**: Evita presentar ofertas aceptadas o pagos pendientes como ventas cobradas y conserva una evidencia verificable de quién confirmó el pago.

**Independent Test**: Aceptar una cotización, comprobar que queda pendiente de pago, confirmar el pago como ADMIN y verificar que queda una venta asociada y la operación puede consultarse por cliente.

**Acceptance Scenarios**:

1. **Given** una cotización aceptada sin pago confirmado, **When** se consulta, **Then** figura aceptada y el pago figura pendiente; no se presenta como venta pagada.
2. **Given** un pago pendiente de una cotización aceptada, **When** un ADMIN registra su confirmación y método/referencia disponibles, **Then** se guarda el actor y fecha, y se registra una sola venta relacionada.
3. **Given** una petición repetida para confirmar el mismo pago, **When** se procesa con la misma clave de idempotencia, **Then** no se duplica el pago ni la venta.
4. **Given** un pago confirmado, **When** se intenta regresar su estado a pendiente sin una operación compensatoria autorizada, **Then** el cambio se rechaza y se conserva la auditoría.

### User Story 5 — Migrar registros y preservar propiedad (Priority: P1)

Las personas del equipo conservan los registros existentes tras la transición, excepto el conjunto de ocho tickets `SALE` que el propietario identificó expresamente como datos de prueba y aprobó eliminar mediante una limpieza acotada. Los clientes del portal quedan asociados a perfiles comerciales; los tickets manuales conservan sus datos capturados; cada cliente autenticado sigue viendo únicamente sus registros.

**Why this priority**: El cambio de modelo no debe perder trazabilidad ni exponer información de otro cliente.

**Independent Test**: Ejecutar la migración en una copia de la base, comparar recuentos y relaciones antes/después y probar aislamiento entre dos cuentas.

**Acceptance Scenarios**:

1. **Given** tickets existentes asociados a una cuenta, **When** se migra la relación, **Then** cada ticket conserva su identificador y queda relacionado con un perfil ligado a esa misma cuenta.
2. **Given** tickets manuales con contacto capturado y sin cuenta, **When** se migran, **Then** se crea un perfil manual por registro legado sin fusionar personas por coincidencia de correo o teléfono.
3. **Given** cotizaciones y pagos existentes que no dependan de los ocho tickets de prueba aprobados para borrar, **When** se migran, **Then** conservan IDs, importes, estados, fechas, líneas, referencias y vínculos válidos.
4. **Given** eventos administrativos de registros que se conservan, **When** se migra el cliente asociado, **Then** el actor y la marca temporal de cada evento permanecen sin cambios.
5. **Given** los ocho tickets `SALE` identificados en la base local como datos de prueba, **When** se aplique la futura limpieza de datos aprobada, **Then** se eliminan solo esos ocho registros y sus dependencias de prueba verificadas; el proceso se aborta si el conjunto esperado no coincide.
6. **Given** que la limpieza de datos de prueba termina, **When** se revisa su informe, **Then** se conservan los conteos previos y posteriores y no se borran tickets de otros tipos ni registros `SALE` ajenos a ese conjunto identificado.

### Edge Cases

- Una cuenta CUSTOMER se desactiva; el perfil comercial y el historial financiero no se borran ni reasignan.
- Un registro legado apunta a un usuario que ya no tiene rol CUSTOMER; la migración conserva la relación para revisión y no elimina datos.
- Un cliente manual más tarde se registra en el portal; no se enlaza automáticamente por coincidencia de correo. La asociación requiere una verificación explícita y queda auditada.
- El perfil comercial modifica teléfono, nombre o correo después de crear un ticket o cotización; los datos históricos definidos como snapshot no cambian retroactivamente.
- Dos solicitudes simultáneas intentan vincular la misma cuenta al mismo tiempo; solo puede prevalecer un perfil vinculado.
- Una cotización de venta no tiene ticket, pero sí cliente; una cotización de servicio debe tener ticket y el mismo cliente asociado.
- Un pago pendiente no debe convertirse en confirmado por una respuesta del LLM ni por el mero hecho de aceptar una cotización.
- Dos clientes intentan aceptar simultáneamente cotizaciones para las mismas últimas unidades; la reserva se concede como máximo hasta el inventario disponible y las demás aceptaciones fallan sin sobreventa.
- Una cotización de venta aceptada conserva la reserva mientras el pago sigue pendiente; al vencer la oferta sin pago confirmado, la reserva se libera.
- La limpieza de los tickets `SALE` de prueba encuentra cantidades o dependencias distintas de las esperadas; debe detenerse y no ejecutar borrados parciales.
- Un fallo a mitad de migración no deja una mezcla en la que una parte de los registros usa la nueva relación y otra parte perdió la anterior.

## Requirements

### Functional Requirements

- **FR-001**: El sistema MUST mantener separadas la cuenta autenticada con permisos/credenciales y la identidad comercial de la persona o empresa atendida.
- **FR-002**: El sistema MUST permitir un perfil comercial sin cuenta de acceso y MUST permitir asociar opcionalmente como máximo una cuenta CUSTOMER activa a cada perfil.
- **FR-003**: El sistema MUST obtener la identidad de portal desde la sesión verificada y resolver el perfil comercial vinculado; MUST rechazar identidad de cliente arbitraria enviada en solicitudes de cliente.
- **FR-004**: El sistema MUST permitir a un ADMIN autorizado buscar, crear, consultar y actualizar perfiles comerciales, sin crear credenciales para clientes manuales.
- **FR-005**: El sistema MUST registrar separadamente el cliente afectado y la cuenta staff que crea, modifica o confirma una operación.
- **FR-006**: Los tickets MUST representar solicitudes de servicio que requieren seguimiento del taller. Una consulta de compra de productos MUST NOT crear por sí sola un ticket de reparación. Los casos de armado o garantía existentes se conservan como tickets solo cuando requieran trabajo/seguimiento del taller.
- **FR-007**: El sistema MUST permitir que un ticket tenga cero o más cotizaciones de servicio, todas del mismo cliente del ticket. El ticket MUST conservarse cuando no hay cotización.
- **FR-008**: Una cotización de venta MUST poder relacionarse directamente con un perfil comercial sin requerir un ticket. Una cotización de servicio MUST relacionarse con un ticket.
- **FR-009**: Una cotización de venta generada para una conversación autenticada MUST guardarse bajo el perfil de la sesión en estado de oferta pendiente antes de presentarse; la respuesta del chat MUST incluir su identificador para consultarla/aceptarla; regenerar o actualizar una oferta MUST conservar el historial sin crear tickets.
- **FR-010**: Cada cotización MUST conservar tipo, cliente, líneas/precios, importe total, estado de oferta, origen, fechas y actor según el tipo de operación.
- **FR-011**: El estado de cotización MUST representar el ciclo de la oferta (pendiente, aceptada, rechazada, vencida o cancelada); el estado de pago MUST representar por separado si el cobro está pendiente, completado, fallido o reembolsado.
- **FR-012**: El sistema MUST registrar una venta/pedido a partir de una cotización de venta aceptada solo cuando el pago tenga confirmación verificable, conservando referencias al cliente, cotización, líneas y pago.
- **FR-013**: La confirmación de pago manual MUST requerir un ADMIN autenticado y conservar su identidad, fecha, método y referencia disponible. Ningún agente LLM puede confirmar un pago.
- **FR-014**: La confirmación repetida de un mismo pago MUST ser idempotente y producir como máximo una venta/pedido.
- **FR-015**: El sistema MUST ofrecer listados administrativos de clientes, tickets, cotizaciones, pagos/ventas y detalles paginados con filtros por los campos relevantes.
- **FR-016**: El sistema MUST permitir a un cliente autenticado consultar solo tickets, cotizaciones, pagos/ventas propios, derivados de su perfil resuelto desde sesión.
- **FR-017**: La salida de un usuario, cambio de correo o desactivación de cuenta MUST NOT borrar ni alterar relaciones históricas del perfil comercial, tickets, cotizaciones, pagos o ventas.
- **FR-018**: El sistema MUST conservar snapshots de contacto y de artículo/precio requeridos para entender históricamente el documento, aunque cambie el perfil o el catálogo.
- **FR-019**: La migración MUST preservar claves, importes, estados, fechas, auditoría y referencias válidas; MUST NOT fusionar perfiles solo por coincidencia de correo/teléfono.
- **FR-020**: La migración MUST ser versionada y admitir ejecución verificable, con recuentos antes/después, restricciones e índices y estrategia de reversión documentada antes de retirar relaciones antiguas.
- **FR-021**: El backend MUST preservar los flujos existentes de reembolso, logística y garantía ligados a tickets/pagos; cualquier relación que no admita una venta sin ticket debe ser identificada y cubierta por una relación a la venta o por un límite de alcance explícito.
- **FR-022**: El backend MUST devolver errores distinguibles para sesión ausente, acceso prohibido, perfil/recurso inexistente, conflicto de vinculación, estado inválido, dato de entrada inválido y almacenamiento no disponible.
- **FR-023**: El backend MUST mantener compatibilidad con los consumidores existentes durante la transición o documentar una versión/cambio de contrato coordinado; este spec no modifica el frontend.
- **FR-024**: Al aceptar una cotización de venta, el sistema MUST reservar de forma atómica las cantidades de sus líneas contra el inventario disponible y MUST rechazar la aceptación completa si no puede reservar todas las unidades. La reserva MUST permanecer activa mientras la oferta aceptada espera el pago; MUST liberarse al rechazar, cancelar o vencer la cotización sin pago confirmado. Al confirmar el pago, el sistema MUST convertir la reserva en salida de inventario vinculada a una única venta/pedido. La aceptación y la confirmación deben ser idempotentes y no permitir sobreventa.
- **FR-025**: La futura migración MUST incluir una limpieza explícita, auditable y limitada a los ocho tickets `SALE` que el propietario identificó como datos de prueba en la base local revisada el 2026-11-03, y a sus registros dependientes confirmados como pertenecientes a esa misma prueba. La limpieza MUST verificar previamente el conjunto esperado y sus dependencias, registrar conteos antes/después, abortar sin borrar si hay discrepancias y no aplicar un borrado genérico a todos los tickets `SALE` ni a otras bases/entornos. Esta limpieza no se ejecuta durante Specify.

### Estado revisado del backend (contexto informativo)

- `users` contiene cuentas/roles y hoy sirve de destino de relaciones de clientes.
- No existe tabla `customers` en el esquema vigente.
- `tickets.customer_id` es nullable y referencia `users`; los tickets manuales guardan contacto en el ticket. `GET /api/admin/customers` busca usuarios activos por correo, no perfiles comerciales independientes.
- `quotes.ticket_id` es obligatorio; las cotizaciones administrativas actuales se crean bajo `/api/admin/tickets/{ticket_id}/quotes`.
- `payments.ticket_id` y `payments.customer_id` son obligatorios; los pagos enlazan cotización opcional y cliente usuario.
- La identidad del chat/portal deriva actualmente del ID de usuario y los repositorios filtran tickets, pagos, reembolsos y garantías a través de esa identidad.
- La base local consultada en modo de solo lectura el 2026-11-03 tiene 26 tablas públicas, 12 tickets (8 SALE, 2 PC_BUILD, 2 SUPPORT), 3 cotizaciones ACCEPTED y 6 pagos PENDING; cuatro tickets SALE tienen pago y dos tienen cotización. No tiene tickets manuales o sin `customer_id` en ese momento. No existe una tabla de registro de migraciones, por lo que el historial aplicado no puede probarse mediante ledger.
- El spec `004-gestion-admin-tickets` permanece intacto como la definición anterior de gestión de tickets; este feature define el nuevo modelo de clientes y contratos complementarios.

### Key Entities

- **Cuenta (`users`)**: identidad autenticada, roles, credenciales y sesión; las claves de cuenta no son un registro comercial.
- **Cliente comercial (`customers`)**: persona o empresa atendida; tiene datos de contacto actuales, origen manual/portal, estado y vínculo opcional único a una cuenta CUSTOMER. No almacena credenciales.
- **Ticket de servicio**: expediente del taller asociado a un cliente y al actor que lo registró; puede existir sin cotizaciones.
- **Cotización**: oferta versionable asociada a un cliente; las ofertas de servicio también se asocian al ticket; las ofertas de venta pueden existir sin ticket.
- **Pago**: intento/registro de cobro asociado al cliente y a la cotización y/o venta; tiene estado independiente, método, referencia y evidencia de confirmación.
- **Venta/Pedido**: operación comercial creada desde una cotización de venta pagada, con estado propio y snapshots de líneas.
- **Evento de auditoría**: acción realizada por cuenta autenticada, actor, fecha y cambios seguros sin copiar credenciales ni textos sensibles.

## Success Criteria

### Measurable Outcomes

- **SC-001**: El 100% de los registros online creados o consultados por un cliente quedan asociados al perfil vinculado a la sesión y ningún escenario de aceptación permite acceso cruzado.
- **SC-002**: El personal puede registrar un cliente manual y crear un ticket o cotización asociado sin crear usuario ni credenciales en el 100% de los escenarios de aceptación.
- **SC-003**: Una solicitud de compra sin actividad de servicio genera cero tickets de reparación.
- **SC-004**: Ninguna venta aparece pagada sin un pago confirmado con actor y fecha verificables.
- **SC-005**: La migración de ensayo conserva el 100% de los registros existentes fuera del conjunto de datos de prueba cuya eliminación fue aprobada, con relaciones válidas o incidencias explícitamente reportadas; el informe enumera por separado cada fila eliminada y su dependencia.
- **SC-006**: Repetir una solicitud de confirmación de pago no crea más de un registro de venta/pedido para la misma operación.

## Assumptions

- El mecanismo de autenticación, cookies, roles y credenciales existentes se mantiene.
- El perfil comercial de un cliente del portal se crea o vincula automáticamente a la cuenta CUSTOMER durante la migración o el primer uso; no se cambia el flujo de autenticación.
- Una cuenta registrada después de una atención manual solo se vincula al perfil manual tras una verificación explícita por personal autorizado; la coincidencia de datos no basta.
- La persona ADMIN confirma manualmente los pagos externos mientras no exista un proveedor de pagos integrado.
- Una cotización aceptada por el cliente inicia el seguimiento de pago; el estado pagado pertenece al pago/venta, no a la oferta.
- Una venta/pedido se registra después de confirmar el pago, conforme a la decisión de negocio anterior del usuario.
- Las especificaciones y contratos aquí descritos son backend; una especificación separada definirá la interfaz frontend.
- La reserva inicia al aceptar una cotización de venta; si la oferta vence sin pago confirmado se libera la reserva. La duración o fecha de vencimiento se define en la oferta y no se fija un plazo global en esta especificación.
- Los ocho tickets `SALE` citados en el snapshot local son datos de prueba según confirmación del propietario y se excluirán mediante limpieza futura con precondiciones, auditoría y conteos verificables; ningún estado de pago se inferirá durante la limpieza.
