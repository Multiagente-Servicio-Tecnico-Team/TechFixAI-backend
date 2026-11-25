# Feature Specification: Gestión administrativa de tickets

**Feature Branch**: `004-gestion-admin-tickets`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Revisar las rutas CRUD de tickets del administrador en el backend contra lo que representa el frontend, determinar si bastan o hay que ampliarlas, y especificar el backend antes de implementarlo en el frontend."

## Clarifications

### Session 2026-11-02

- Q: ¿Cómo quieres registrar un ticket presencial cuando el cliente no tiene una cuenta en el sistema? → A: Guardar nombre, teléfono y correo opcional directamente en el ticket presencial, permitiendo que no tenga una cuenta de usuario asociada.
- Q: ¿Quieres conservar las tres categorías del frontend como clasificación visible del ticket y mantener además el tipo operativo actual para los flujos internos? → A: Usar los mismos tipos operativos del backend y traducir sus nombres en la interfaz; enviar al backend el valor canónico del tipo seleccionado, sin añadir una clasificación paralela.
- Q: ¿Cómo quieres manejar el adelanto que el formulario permite ingresar al crear un ticket presencial? → A: El ticket debe guardar costo e información del método de pago como atributos propios, y registrar si su origen es manual o en línea.
- Q: En el formulario actual, ¿el importe debe representar el adelanto recibido al crear el ticket o el costo total estimado del servicio? → A: El importe representa el adelanto recibido; la cotización posterior contiene el costo total y queda relacionada con el ticket.
- Q: ¿Quieres que el tablero muestre todos los estados del backend con etiquetas en español, enviando el valor original al guardar? → A: Mostrar todos los estados canónicos del backend con etiquetas traducidas en la interfaz y enviar el código original al guardar.
- Q: ¿En el formulario de creación quieres conservar solo Reparación, Venta y Soporte, o mostrar todos los tipos que acepta el backend con sus etiquetas en español? → A: Mostrar todos los tipos del backend traducidos, incluidos Armado de PC y Garantía.

## User Scenarios & Testing

### User Story 1 - Consultar y filtrar tickets del taller (Priority: P1)

El administrador abre el tablero del taller y consulta tickets con identificador, fecha, cliente, contacto, equipo, detalle, tipo de solicitud, importe y estado. Puede buscar por cliente, equipo o identificador, y filtrar por tipo de solicitud y estado para organizar el trabajo.

**Why this priority**: El tablero es la vista principal para gestionar la cola de trabajo. El frontend debe mostrar todos los tipos operativos disponibles con etiquetas en español y enviar el valor canónico correspondiente al backend.

**Independent Test**: Con tickets de distintos clientes, tipos y estados, consultar la lista y comprobar que cada búsqueda y filtro devuelve únicamente los registros coincidentes, con paginación estable.

**Acceptance Scenarios**:

1. **Given** tickets de varios clientes y estados, **When** un administrador lista los tickets sin filtros, **Then** recibe resultados paginados con los datos necesarios para las tarjetas del tablero.
2. **Given** tickets con distintos tipos de solicitud, estados y clientes, **When** el administrador combina búsqueda, tipo y estado, **Then** todos los filtros se aplican conjuntamente y los metadatos de paginación reflejan el resultado filtrado.
3. **Given** un identificador de ticket, nombre/contacto del cliente, equipo o detalle, **When** el administrador busca ese valor, **Then** encuentra los tickets coincidentes sin distinguir mayúsculas y minúsculas.

### User Story 2 - Registrar un ticket recibido en mostrador (Priority: P1)

El administrador registra un ticket presencial incluyendo los datos que la pantalla de recepción solicita: cliente y contacto, equipo, motivo de ingreso y tipo de solicitud. La interfaz muestra el nombre traducido de cada tipo disponible y envía el valor canónico al backend. El sistema asigna un identificador único y deja el ticket en un estado inicial coherente.

**Why this priority**: El frontend presenta la creación manual como una acción central. La ruta actual exige correo, título y detalle; la pantalla también recoge teléfono, nombre, tipo de solicitud y un posible adelanto, que deben integrarse sin crear una clasificación incompatible.

**Independent Test**: Crear un ticket presencial sin cuenta de usuario y comprobar que aparece en el tablero y detalle con los datos de contacto capturados.

**Acceptance Scenarios**:

1. **Given** datos válidos de contacto e ingreso presencial, **When** el administrador crea un ticket, **Then** el sistema conserva el contacto en el ticket, no exige una cuenta, genera un código único y devuelve el detalle.
2. **Given** una solicitud iniciada por un usuario autenticado, **When** el sistema crea el ticket en línea, **Then** lo asocia a esa cuenta para que el cliente pueda consultarlo en su portal.
3. **Given** un dato obligatorio ausente o inválido, **When** se intenta crear el ticket, **Then** el sistema informa validación y no persiste parcialmente el registro.
4. **Given** los datos de contacto de un cliente presencial, el equipo/marca/modelo y el detalle de la solicitud, **When** el administrador registra el ticket, **Then** el ticket conserva estos datos y el backend recibe el valor canónico del tipo elegido en español sin exigir ni crear una cuenta de usuario.
5. **Given** un ticket manual o en línea, **When** el sistema lo guarda, **Then** el ticket conserva su origen y el adelanto/método de pago informados; una cotización posterior registra el costo total y queda relacionada al ticket sin sustituir el adelanto.

### User Story 3 - Revisar detalle y actualizar el estado (Priority: P1)

El administrador abre un ticket, revisa cliente, equipo, solicitud, datos financieros disponibles e historial temporal, y cambia su estado entre los valores canónicos admitidos por el backend.

**Why this priority**: El tablero permite mover tarjetas y la vista de detalle guarda cambios de estado. Todos los estados canónicos del backend deben estar representados en español, sin fusionar estados distintos.

**Independent Test**: Obtener un ticket, asignarle un estado canónico admitido por el backend, volver a consultarlo y verificar que el estado y la fecha de actualización sean los mismos.

**Acceptance Scenarios**:

1. **Given** un ticket existente, **When** el administrador consulta su detalle, **Then** recibe cliente, teléfono, correo, equipo, descripción, tipo de solicitud, fechas, estado y cotización/pago relacionados cuando existan.
2. **Given** cualquier estado canónico admitido, **When** el administrador guarda el cambio, **Then** el estado queda actualizado y se conserva la fecha de modificación.
3. **Given** un código de estado inexistente, **When** el administrador intenta guardarlo, **Then** el sistema rechaza el cambio sin alterar el registro.
4. **Given** un identificador que no corresponde a un ticket, **When** se solicita el detalle o se actualiza, **Then** el sistema responde que no existe.
5. **Given** cualquier estado canónico admitido por el backend, **When** el ticket se presenta en el tablero o detalle, **Then** se muestra su etiqueta en español y al guardar se conserva el código original.

### User Story 4 - Mantener trazabilidad y exportar resultados (Priority: P2)

El administrador puede obtener de forma completa el conjunto filtrado de tickets que usa para elaborar un reporte y puede identificar cuándo fue creado o actualizado cada registro. Los cambios administrativos se atribuyen a la cuenta autenticada.

**Why this priority**: El frontend ofrece exportación CSV y muestra fechas; para que el reporte refleje datos reales y los cambios sean auditables, la API debe permitir recorrer los resultados filtrados y reconocer quién hizo los cambios.

**Independent Test**: Aplicar filtros, recorrer todas las páginas sin duplicar ni omitir tickets y comparar el conjunto con el reporte; comprobar que una actualización conserva autor y fecha verificables.

**Acceptance Scenarios**:

1. **Given** más resultados que el tamaño de una página, **When** el administrador recorre las páginas con el mismo filtro, **Then** cada ticket aparece exactamente una vez y el total del conjunto filtrado es consistente.
2. **Given** una creación o modificación realizada por un administrador autenticado, **When** se revisa la trazabilidad del ticket, **Then** se identifica la cuenta responsable y el momento del cambio.
3. **Given** un ticket existente, **When** el administrador solicita darlo de baja, **Then** el ticket se conserva y se marca como cancelado para preservar la trazabilidad y sus registros relacionados.

### Edge Cases

- Búsqueda vacía o compuesta solo por espacios: se interpreta como ausencia de búsqueda.
- Un filtro contiene un estado o tipo de solicitud no admitidos: se rechaza con validación, sin devolver silenciosamente resultados distintos.
- Un contacto se modifica posteriormente en el perfil del cliente: el detalle debe distinguir los datos actuales del cliente de cualquier dato histórico que se haya decidido conservar en el ticket.
- Una página solicitada queda fuera del rango tras aplicar filtros: se devuelve una página vacía con metadatos coherentes.
- El ticket tiene pagos, cotizaciones u otros registros asociados: se cancela conservando tanto el ticket como sus relaciones; no se permite borrado físico.
- Un adelanto no informado deja vacíos sus atributos de importe y método; un método no puede presentarse como pagado si no se informó un importe.
- Un estado canónico no reconocido por una versión de la interfaz se muestra como desconocido de forma segura y no se transforma en otro estado al guardar.

## Requirements

### Functional Requirements

- **FR-001**: El sistema MUST permitir que solo una cuenta autenticada con rol `ADMIN` liste, consulte, cree, modifique y gestione tickets de taller.
- **FR-002**: El sistema MUST proporcionar una lista paginada y ordenada de tickets con el identificador, fechas, cliente, datos de contacto disponibles, equipo, descripción, tipo de solicitud, estado, origen y datos monetarios relacionados que existan.
- **FR-003**: El sistema MUST permitir combinar búsqueda de texto, tipo de solicitud y estado; las consultas de lista y exportación deben utilizar los mismos criterios.
- **FR-004**: El sistema MUST permitir registrar tickets presenciales con nombre y teléfono de contacto y correo opcional, sin requerir una cuenta ni crear credenciales ficticias.
- **FR-005**: El sistema MUST permitir crear tickets asociados a una cuenta autenticada para los flujos en línea y tickets manuales con contacto propio guardado en el ticket; cada origen debe ser distinguible como `ONLINE` o `MANUAL`, y la asociación de cuenta es obligatoria para `ONLINE` y opcional para `MANUAL`.
- **FR-006**: El sistema MUST validar los datos de contacto presenciales, el equipo/marca/modelo obligatorio capturado como un solo texto, el detalle obligatorio de la falla o solicitud y el tipo de solicitud. El texto de equipo/marca/modelo se conserva como título del ticket y el detalle se conserva como descripción.
- **FR-007**: La interfaz MUST presentar todos los tipos de solicitud admitidos por el backend con etiquetas en español: `REPAIR` (Reparación), `SALE` (Venta), `PC_BUILD` (Armado de PC), `SUPPORT` (Soporte) y `WARRANTY_CLAIM` (Reclamo de garantía). MUST enviar el código canónico seleccionado.
- **FR-008**: El sistema MUST generar un código de ticket único y asignar el estado inicial configurado por las reglas del negocio.
- **FR-009**: El sistema MUST devolver un detalle completo de ticket que incluya datos de contacto, equipo, motivo, tipo de solicitud, fechas, estado y cotización/pago relacionados cuando existan.
- **FR-010**: El sistema MUST permitir al administrador actualizar los campos editables y asignar cualquier estado canónico existente; debe rechazar códigos no admitidos y actualizar la fecha de modificación.
- **FR-011**: La interfaz MUST mostrar todos los estados canónicos admitidos por el backend con etiquetas en español diferenciadas y MUST enviar el código canónico original al actualizar el estado.
- **FR-012**: El sistema MUST conservar trazabilidad de creación y modificaciones administrativas, incluyendo cuenta responsable y fecha, conforme a las capacidades del esquema existente o a una migración aprobada.
- **FR-013**: El sistema MUST guardar en el ticket el importe del adelanto recibido y su método de pago cuando se informen, separados del costo total de la cotización; si hay adelanto, debe indicarse un método entre Yape/Plin, efectivo y tarjeta.
- **FR-014**: El sistema MUST permitir crear posteriormente una cotización con el costo total y asociarla al ticket correspondiente; la cotización no debe reemplazar ni reinterpretar los atributos del adelanto.
- **FR-015**: El sistema MUST conservar los tickets y sus registros relacionados, y MUST ofrecer cancelación en lugar de borrado físico.
- **FR-016**: El sistema MUST devolver resultados y errores distinguibles para sesión ausente, permisos insuficientes, recurso inexistente, datos inválidos, conflicto de integridad y almacenamiento no disponible.
- **FR-017**: El sistema MUST mantener separado el listado de tickets del administrador del listado de tickets propios del cliente, filtrando este último por la asociación a la cuenta autenticada y nunca incluyendo tickets presenciales sin esa asociación.
- **FR-018**: La lista administrativa MUST permitir recorrer el conjunto filtrado de forma estable para que el frontend exporte todos los resultados, no solo la página actual.

### Key Entities

- **Ticket**: Solicitud de reparación, venta, armado, soporte o garantía, con código, título/equipo, detalle, tipo de solicitud, estado, origen (`MANUAL` o `ONLINE`), datos de contacto y, cuando corresponda, adelanto recibido y método de pago.
- **Contacto del ticket**: Nombre, teléfono y correo opcional capturados para la solicitud. En tickets presenciales se guardan en el ticket sin crear una cuenta; en tickets autenticados se relacionan con la cuenta propietaria.
- **Cuenta de cliente**: Usuario autenticado que puede consultar únicamente los tickets vinculados a su propia cuenta.
- **Cuenta administradora**: Identidad autenticada que administra tickets y debe quedar asociada a los cambios realizados.
- **Cotización y pago**: Registros relacionados con el ticket; la cotización posterior expresa el costo total, mientras que los atributos de adelanto del ticket no confirman por sí solos una operación en el registro transaccional de pagos.
- **Historial de estado**: Evidencia de cambios de estado, fecha y cuenta que ejecutó el cambio, si el esquema actual no ofrece ya esta trazabilidad.

## Success Criteria

### Measurable Outcomes

- **SC-001**: El administrador puede encontrar un ticket por código, cliente o equipo y aplicar dos filtros combinados con resultados correctos en el 100% de los casos de aceptación.
- **SC-002**: El 100% de los tickets devueltos en lista y detalle contiene los campos requeridos por las tarjetas y la vista de detalle del frontend o declara explícitamente que el dato relacionado no existe.
- **SC-003**: Crear o cambiar el estado de un ticket produce una respuesta persistida que coincide con la siguiente consulta del mismo ticket.
- **SC-004**: Recorrer la lista completa filtrada no omite ni duplica registros, aun cuando el resultado supere una página.
- **SC-005**: Ninguna cuenta distinta de `ADMIN` puede usar operaciones administrativas, y ninguna operación de tickets de cliente permite consultar tickets de otra cuenta.
- **SC-006**: Ninguna eliminación administrativa causa pérdida o corrupción de cotizaciones, pagos o evidencia relacionada.

## Assumptions

- La fuente de datos es el esquema ampliado de PostgreSQL ya adoptado por el backend; cualquier cambio estructural se especificará como migración trazable y no se ejecutará en esta fase.
- Las operaciones administrativas existentes son el punto de partida y deben conservar compatibilidad donde ya satisfagan requisitos.
- El frontend inspeccionado aún usa estado local de demostración para el tablero, creación y detalle; por tanto, esta especificación define el contrato backend que permitirá conectarlo después.
- Los tickets iniciados por usuarios autenticados permanecen asociados a su cuenta para que aparezcan en el portal; los tickets presenciales pueden no tener cuenta y conservan nombre, teléfono y correo opcional en el ticket.
- Los datos de contacto capturados en el ticket presencial representan la información recibida al momento del ingreso; no crean ni modifican por sí mismos un usuario del sistema.
- El frontend mantiene los valores canónicos de tipos de solicitud del backend y solo traduce sus etiquetas visibles; no se añade una categoría paralela en la base de datos.
- En creación, el selector que hoy se etiqueta “Categoría” se amplía para mostrar todos los tipos anteriores; no se conserva como un campo separado de tres categorías.
- El frontend mantiene todos los estados canónicos admitidos por el backend, con etiquetas en español y los mismos códigos al guardar; no los agrupa en las seis etapas de demostración actuales.
- El administrador puede asignar cualquiera de los estados canónicos existentes; no se exige una secuencia rígida de transiciones en esta versión.
- El ticket guardará su origen (`MANUAL` o `ONLINE`), adelanto recibido y método de pago como atributos propios. La cotización se genera posteriormente con el costo total y se asocia al ticket; no equivale al adelanto.
- La exportación CSV sigue siendo responsabilidad del frontend; el backend debe permitir obtener la totalidad del conjunto filtrado.
- Los tickets no se borran físicamente desde la gestión administrativa; se cancelan para conservar trazabilidad y relaciones.
- El importe y método de adelanto se capturan como atributos del ticket y no confirman por sí solos un pago transaccional. La cotización posterior conserva el costo total y se asocia al ticket.
