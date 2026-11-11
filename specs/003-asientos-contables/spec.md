# Feature Specification: Registro y trazabilidad de asientos contables

**Feature Branch**: `003-asientos-contables`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Agregar en el backend rutas API GET, POST y las necesarias para manejar asientos contables según SUNAT; solo una persona autorizada que no sea customer podrá operarlas. Registrar fecha, concepto, detalle, categoría, responsable y monto, guardar las tablas que falten y entregar el detalle necesario para una vista del asiento en el frontend. El frontend tendrá su propia especificación en su repositorio."

## Clarifications

### Session 2026-11-02

- Q: Cuando dices «según SUNAT», ¿quieres un registro contable interno o también generar libros electrónicos PLE para presentarlos? → A: Solo registro interno; no generar ni presentar PLE.
- Q: ¿Qué roles deben poder usar las operaciones contables: solo `ADMIN`, `ADMIN` y `TECHNICIAN`, o un nuevo rol específico de contabilidad? → A: Solo `ADMIN`; `CUSTOMER` y `TECHNICIAN` quedan excluidos.
- Q: En cada asiento, ¿«responsable» debe ser quien lo registró con su cuenta o una persona asignada que puede ser distinta? → A: Responsable es quien registra; se obtiene de la sesión autenticada.
- Q: ¿Cada asiento debe tener líneas contables con importes al debe y al haber que sumen lo mismo, o basta con guardar un monto general? → A: Líneas de debe/haber balanceadas, con al menos dos líneas; el total es el monto resumen.
- Q: ¿Un asiento debe quedar confirmado apenas se registra o primero debe quedar en borrador para que un `ADMIN` lo revise y confirme después? → A: Se registra confirmado en una sola operación.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Registrar un asiento balanceado (Priority: P1)

Una persona administradora autorizada registra una operación con fecha, concepto, detalle, categoría y sus líneas contables. Cada línea identifica una cuenta y su movimiento al debe o al haber. El sistema conserva quién registró el asiento y la fecha de registro, lo crea confirmado solo cuando el total del debe coincide con el total del haber y desde entonces no permite editarlo ni eliminarlo.

**Why this priority**: Sin un asiento íntegro y balanceado no hay un registro contable confiable que consultar.

**Independent Test**: Con una sesión administrativa, registrar un asiento con dos o más líneas balanceadas y verificar que queda confirmado con correlativo, fecha de operación, concepto, categoría, responsable y total. Intentar otro con importes desbalanceados y verificar que no se persiste.

**Acceptance Scenarios**:

1. **Given** una sesión activa de una cuenta `ADMIN`, **When** envía una operación con fecha, concepto, categoría y líneas de debe/haber balanceadas, **Then** se crea en una sola operación un asiento confirmado con número correlativo, moneda PEN, total y marcas temporales, y el responsable se obtiene de la sesión.
2. **Given** un asiento con líneas incompletas, importes negativos/cero o totales distintos entre debe y haber, **When** intenta registrarlo, **Then** el sistema rechaza la operación con un error de validación y no guarda un asiento parcial.
3. **Given** una sesión ausente o inválida, **When** intenta crear un asiento, **Then** recibe `401` y no se crea ningún dato.
4. **Given** una cuenta `CUSTOMER` o `TECHNICIAN`, **When** intenta crear un asiento, **Then** recibe `403` y no se crea ningún dato.
5. **Given** una solicitud de creación que ya fue aceptada, **When** el cliente reintenta la misma operación con su misma referencia de solicitud, **Then** recibe el resultado ya creado y no se genera otro asiento.

### User Story 2 - Consultar y presentar el detalle del asiento (Priority: P2)

Una persona autorizada lista los asientos y consulta el detalle de uno para revisar la operación. La respuesta permite a otro cliente construir una vista con los datos generales, las líneas contables, sus importes, los totales, la categoría, el responsable, las fechas y el estado.

**Why this priority**: El registro aporta valor operativo cuando se puede encontrar y revisar con su contexto y procedencia.

**Independent Test**: Crear un asiento, listarlo por rango de fechas y categoría, abrir su detalle y comprobar que coinciden todas las líneas, totales, responsable y fechas con lo registrado.

**Acceptance Scenarios**:

1. **Given** asientos registrados, **When** una cuenta `ADMIN` consulta el listado, **Then** recibe resultados paginados y puede filtrar por fecha, categoría, estado y correlativo.
2. **Given** un identificador existente, **When** una cuenta `ADMIN` consulta el detalle, **Then** recibe concepto, detalle, fecha de operación, categoría, correlativo, estado, moneda, total, responsable, fechas de auditoría y todas las líneas con cuenta, descripción, debe y haber.
3. **Given** un identificador inexistente, **When** se consulta el detalle, **Then** la API responde `404` sin revelar información de otros registros.
4. **Given** una cuenta no autorizada, **When** consulta listado o detalle, **Then** recibe `401` o `403` según el estado de su sesión.

### User Story 3 - Corregir un asiento confirmado conservando trazabilidad (Priority: P3)

Una persona autorizada corrige un asiento confirmado mediante un asiento inverso relacionado con el original y con una razón explícita. No puede modificar ni eliminar el asiento original. La consulta conserva las fechas, responsables y eventos de ambos.

**Why this priority**: Los datos contables confirmados deben poder auditarse sin perder la versión que originó el registro.

**Independent Test**: Crear un asiento y comprobar que ya no admite edición o eliminación; registrar su reversión y consultar el vínculo, la razón y ambos responsables/fechas.

**Acceptance Scenarios**:

1. **Given** un asiento confirmado, **When** una cuenta `ADMIN` solicita modificarlo o eliminarlo, **Then** la API rechaza la operación y mantiene intacto el registro.
2. **Given** un asiento confirmado, **When** una cuenta `ADMIN` solicita revertirlo con una razón, **Then** se crea un asiento inverso relacionado, con debe/haber intercambiados, fecha y responsable propios, y el original queda identificado como revertido.
3. **Given** un asiento ya revertido, **When** se solicita revertirlo otra vez, **Then** la API rechaza la reversión duplicada y conserva el historial existente.

### Edge Cases

- Dos personas registran asientos al mismo tiempo: cada uno recibe un correlativo único sin duplicados.
- Dos solicitudes concurrentes reintentan la misma creación: se acepta un único asiento y ambas reciben el mismo resultado.
- Un reintento de creación por error de red no debe crear duplicados si la misma operación ya fue aceptada.
- La fecha de operación puede diferir de la fecha de creación; ambas se muestran por separado y no se sustituyen entre sí.
- Un asiento puede contener más de dos líneas, siempre que cada línea tenga exactamente un movimiento positivo en debe o haber y ambos totales coincidan.
- Categoría, concepto, detalle o cuenta faltantes, demasiado extensos o con formato inválido se rechazan antes de guardar.
- Una cuenta autorizada desactivada o con sesión expirada no puede crear, consultar ni modificar registros.
- Un asiento vinculado a otro como reversión no puede revertirse repetidamente ni generar ciclos de referencias.
- El detalle de un asiento nunca incluye contraseñas, tokens de sesión ni datos sensibles que no sean necesarios para la trazabilidad contable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: La API debe permitir exclusivamente a una sesión activa con rol `ADMIN` crear, consultar y revertir registros contables. `CUSTOMER` y `TECHNICIAN` no pueden acceder; una cuenta sin sesión recibe `401` y una cuenta autenticada sin permiso recibe `403`.
- **FR-002**: La API debe exponer operaciones para listar y filtrar asientos, crear un asiento confirmado en una sola operación, obtener el detalle y registrar la reversión de un asiento confirmado. La edición y eliminación física de asientos confirmados están prohibidas.
- **FR-003**: La API debe permitir consultar las categorías activas de asientos para que las personas autorizadas usen valores controlados al registrar operaciones.
- **FR-004**: El listado debe aceptar paginación y filtros por rango de fecha de operación, categoría, estado y correlativo, y devolver metadatos suficientes para continuar la paginación.
- **FR-005**: Cada asiento debe conservar correlativo único, fecha de operación, concepto/glosa, detalle, categoría, moneda PEN, estado, total, identidad del responsable, fecha de creación y fecha de última actualización.
- **FR-006**: Cada asiento debe contener dos o más líneas con código y denominación de cuenta, detalle opcional, importe al debe o al haber y total de línea. El sistema no afirmará que los códigos o denominaciones fueron validados contra un catálogo oficial si tal catálogo no está configurado.
- **FR-007**: Cada línea debe tener un importe decimal positivo en exactamente uno de los lados (debe o haber); el total del debe debe coincidir exactamente con el total del haber antes de crear el asiento confirmado. El total del asiento será ese total coincidente.
- **FR-008**: Las categorías deben ser valores controlados y consultables, para evitar que el listado se fragmente por variaciones de escritura. Un asiento conserva la categoría aplicada aunque esta deje de estar disponible para nuevos registros.
- **FR-009**: El detalle consultado debe devolver en una sola representación el encabezado, todas las líneas en orden, totales de debe y haber, correlativo, categoría, estado, responsable, fechas, historial de acciones y relación con asiento original/reversión cuando exista.
- **FR-010**: El responsable que realiza la operación y los campos de auditoría deben derivarse de la sesión autenticada del backend; la API no debe confiar en un identificador de responsable enviado por el cliente.
- **FR-011**: El sistema debe registrar de manera inmutable quién creó o revirtió cada asiento y cuándo, junto con el tipo de acción y la referencia a la operación relacionada. La auditoría no debe incluir credenciales ni contenido ajeno al registro contable.
- **FR-012**: Cada asiento se crea confirmado y sus datos contables quedan inmutables desde su creación. Una corrección posterior solo puede registrarse mediante reversión vinculada.
- **FR-013**: La reversión debe requerir una razón, relacionarse con el asiento original y crear movimientos de signo opuesto intercambiando debe y haber. El asiento original no se elimina ni se reescribe; no se permite reversión duplicada.
- **FR-014**: El sistema debe identificar una solicitud de creación mediante una referencia única del cliente; al reintentar una operación ya aceptada debe devolver su resultado y no crear un segundo asiento confirmado.
- **FR-015**: Las operaciones que escriben el encabezado, las líneas, el evento de auditoría, el correlativo y los vínculos de reversión deben ser atómicas: si una parte falla, ninguna parte debe quedar persistida.
- **FR-016**: Los errores de validación, permiso, conflicto de estado, correlativo duplicado y recurso inexistente deben devolver respuestas consistentes que no expongan SQL, trazas, secretos ni datos de otras cuentas.
- **FR-017**: El backend debe persistir los registros y su historial de forma durable, relacionando al responsable con la cuenta existente y evitando que la eliminación de una cuenta borre la evidencia contable.
- **FR-018**: La información entregada por la API debe permitir construir en el repositorio frontend una vista de detalle; el alcance de esta feature no incluye cambios al repositorio ni a la interfaz del frontend.
- **FR-019**: La función no debe declarar que presenta libros electrónicos a SUNAT, que valida obligaciones tributarias de un contribuyente ni que reemplaza la revisión de un profesional contable.

### Key Entities *(include if feature involves data)*

- **Asiento contable**: Operación identificada por correlativo con fecha, concepto, detalle, categoría, moneda, estado, totales, responsable y marcas temporales.
- **Línea contable**: Cuenta y movimiento de debe o haber que integra el asiento; conserva código/denominación y su importe histórico.
- **Categoría contable**: Clasificación controlada para filtrar y presentar asientos.
- **Responsable**: Cuenta activa de personal autenticado que ejecutó una acción; no es un valor arbitrario enviado por el cliente.
- **Evento de auditoría**: Acción sobre un asiento, actor, fecha y referencia al registro afectado, conservado aunque cambie su estado posterior.
- **Reversión**: Asiento que compensa uno confirmado y mantiene una referencia verificable al registro original y su razón.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las solicitudes de creación, consulta o reversión de un `CUSTOMER` o `TECHNICIAN` son rechazadas y no producen cambios persistentes.
- **SC-002**: El 100% de los asientos confirmados tienen totales de debe y haber iguales y al menos dos líneas válidas.
- **SC-003**: Una persona autorizada puede recuperar el detalle completo de un asiento en una sola consulta y cada campo presentado coincide con el registro almacenado.
- **SC-004**: El 100% de las operaciones de creación y reversión exitosas identifican actor y fecha en el historial.
- **SC-005**: Ningún asiento confirmado puede alterarse o eliminarse; el 100% de correcciones posteriores se representan como una reversión relacionada.
- **SC-006**: En pruebas de concurrencia, el 100% de correlativos asignados son únicos y una solicitud de creación solo puede producir un asiento confirmado.

## Assumptions

- La versión inicial es un registro interno de operaciones, no un sistema de declaración tributaria ni de generación/envío PLE. SUNAT publica requisitos distintos según libro, modalidad y obligación del contribuyente; estos deben revisarse con un contador antes de ampliar el alcance.
- El personal autorizado se limita al rol `ADMIN` existente, dado que el backend ya lo utiliza para rutas administrativas; las cuentas `TECHNICIAN` no se consideran autorizadas para asientos en esta versión.
- La moneda inicial es PEN, consistente con las operaciones comerciales documentadas en el proyecto.
- El correlativo será único y global para el sistema, sin reinicio mensual o anual en esta versión interna; la numeración requerida para una eventual exportación PLE queda fuera de alcance.
- El responsable de la operación es la persona autenticada que la ejecuta. Si se requiere asignar un responsable distinto, será un requisito separado con auditoría de ambos actores.
- La categoría se mantiene como catálogo controlado por el sistema; sus valores iniciales se decidirán en planificación a partir de los casos operativos confirmados.
- Los códigos de cuenta y denominaciones se conservan tal como los proporciona el personal autorizado. No se presume que el backend tenga cargado un Plan Contable General Empresarial oficial y vigente.
- Al redactar este spec, el esquema base de referencia aún no representaba asientos contables, líneas ni eventos de auditoría. La migración 003 implementó esas entidades en la BD actual; comprobar la instantánea `contexto/tablas postgres v2.sql` para el estado vigente. Esta nota conserva el razonamiento original del feature.
- El repositorio del frontend es independiente y recibirá después una especificación propia basada en el contrato de detalle del backend.

## Referencias normativas consultadas

- [SUNAT, Formato 5.1: Libro Diario](https://contenido.app.sunat.gob.pe/insc/Libros%2By%2BRegistros/Informacion%2Bm%C3%ADnimo%2Bformatos/FORMATO_5_1.pdf): identifica entre la información mínima correlativo/código único, fecha, glosa, cuenta contable con código/denominación, debe, haber y totales.
- [SUNAT, Libros y registros contables obligatorios](https://emprender.sunat.gob.pe/comprobantes-libros/registros-libros-electronicos/libros-registros-contables-obligatorios): la obligación depende de las características y condiciones tributarias del contribuyente.

Esta referencia informa campos relevantes para el diseño; no certifica que el producto genere un Libro Diario electrónico ni que satisfaga por sí solo las obligaciones tributarias aplicables.
