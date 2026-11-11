# Feature Specification: Catálogo de cuentas y consultas contables

**Feature Branch**: `009-catalogo-cuentas-consultas-contables`

**Created**: 2026-11-09

**Status**: Draft

**Input**: User description: "Definir para el backend un catálogo de cuentas contables y consultas contables, usando por defecto un plan peruano PCGE, con posibilidad de crear planes propios, periodos mensuales con cierre y reapertura auditados, y reportes de diario, mayor y balance de comprobación exportables a CSV y XLSX."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar y administrar planes de cuentas (Priority: P1)

Una persona ADMIN consulta el plan contable predeterminado de Perú, navega su jerarquía y consulta la versión y procedencia de sus cuentas. También puede crear un plan alternativo para la organización y mantener sus cuentas sin alterar planes ni asientos históricos.

**Why this priority**: El catálogo controlado evita capturar códigos y nombres inconsistentes en nuevas líneas contables y es la base de las consultas por cuenta.

**Independent Test**: Con una sesión ADMIN, consultar el plan predeterminado y sus cuentas jerárquicas; crear un plan alternativo y comprobar que ambos son identificables y que el predeterminado sigue seleccionado hasta que un ADMIN lo cambie explícitamente.

**Acceptance Scenarios**:

1. **Given** que existe el plan inicial peruano, **When** un ADMIN consulta planes y cuentas, **Then** recibe el nombre, jurisdicción, edición, fuente, vigencia, estado y jerarquía del plan predeterminado.
2. **Given** una sesión ADMIN, **When** crea un plan propio con cuentas válidas, **Then** el plan queda separado del plan inicial y puede consultarse sin cambiar el predeterminado automáticamente.
3. **Given** una cuenta que ya fue usada, **When** un ADMIN intenta eliminarla o cambiar sus datos identificadores, **Then** la operación conserva el historial y exige desactivarla o crear una nueva versión en su lugar.
4. **Given** una cuenta sin permiso, **When** consulta o administra los planes, **Then** recibe `401` o `403` sin obtener ni modificar información contable.

### User Story 2 - Registrar asientos con cuentas del plan (Priority: P1)

Una persona ADMIN registra un asiento confirmado seleccionando cuentas habilitadas del plan vigente. El sistema valida que las cuentas sean imputables, conserva una referencia al catálogo y guarda el código y nombre aplicados como snapshot para que los cambios posteriores del plan no reescriban el asiento.

**Why this priority**: Las líneas de los nuevos asientos deben poder agruparse y consultarse con cuentas consistentes, sin perder el dato histórico que se registró.

**Independent Test**: Crear un asiento balanceado con cuentas seleccionadas del plan; comprobar que sus líneas guardan la identificación y el snapshot de cada cuenta. Desactivar o renombrar después una cuenta y verificar que el asiento previo mantiene los datos originales y que la cuenta desactivada no se ofrece para nuevos asientos.

**Acceptance Scenarios**:

1. **Given** un periodo abierto y un plan seleccionado, **When** un ADMIN crea un asiento balanceado con cuentas imputables del mismo plan, **Then** el asiento se confirma y cada línea conserva cuenta, código, denominación e importes.
2. **Given** una cuenta inexistente, desactivada, no imputable o de otro plan, **When** se intenta usar en una línea, **Then** se rechaza toda la operación y no queda un asiento parcial.
3. **Given** una línea histórica sin vínculo al nuevo catálogo, **When** se consulta el asiento o se generan reportes, **Then** conserva y presenta su código y denominación existentes sin asignación automática a una cuenta nueva.
4. **Given** una cuenta con asientos asociados, **When** se modifica el nombre o vigencia del catálogo, **Then** los snapshots de asientos ya confirmados no cambian.

### User Story 3 - Gestionar periodos contables mensuales (Priority: P1)

Una persona ADMIN consulta periodos mensuales y puede cerrarlos o reabrirlos con registro de actor, fecha, acción y motivo. Los asientos nuevos y las reversiones solo se aceptan con fecha de operación dentro de un periodo abierto.

**Why this priority**: El cierre evita registrar operaciones en periodos que ya fueron revisados y permite corregirlos de forma controlada y auditable.

**Independent Test**: Crear un periodo mensual abierto, cerrarlo, comprobar que un asiento fechado en ese mes se rechaza, reabrirlo con motivo y comprobar que la operación se permite; verificar los dos eventos de auditoría.

**Acceptance Scenarios**:

1. **Given** un periodo mensual abierto, **When** un ADMIN lo cierra, **Then** el periodo queda cerrado y el sistema registra quién lo cerró, cuándo y el estado anterior y nuevo.
2. **Given** un periodo cerrado, **When** se solicita crear o revertir un asiento con fecha en ese mes, **Then** la operación se rechaza sin escritura parcial.
3. **Given** un periodo cerrado, **When** un ADMIN lo reabre indicando un motivo, **Then** queda abierto y se registra el actor, fecha, motivo y transición en el historial.
4. **Given** el periodo ya está en el estado solicitado, **When** se repite la transición, **Then** la API devuelve un conflicto de estado y no duplica eventos.

### User Story 4 - Consultar y exportar reportes contables (Priority: P1)

Una persona ADMIN consulta el diario, el mayor por cuenta y el balance de comprobación para un periodo o rango de fechas. Puede aplicar filtros disponibles y exportar cada reporte a CSV o XLSX con los mismos datos y criterios que la vista consultada.

**Why this priority**: Los reportes convierten los asientos en consultas de control y conciliación sin requerir revisar cada asiento individualmente.

**Independent Test**: Registrar varios asientos balanceados, incluidos uno revertido y su reversión; consultar los tres reportes para el mismo rango y comparar cuentas, movimientos y totales con los asientos fuente. Exportar cada reporte en ambos formatos y verificar que filtros y cifras coinciden.

**Acceptance Scenarios**:

1. **Given** asientos dentro del rango consultado, **When** ADMIN solicita el diario, **Then** recibe asientos ordenados por fecha y correlativo, con fecha, concepto, cuenta, debe, haber, totales y estado de reversión.
2. **Given** un plan y una cuenta seleccionados, **When** ADMIN solicita el mayor, **Then** recibe movimientos de esa cuenta, ordenados cronológicamente, con saldo acumulado y referencias a los asientos.
3. **Given** un periodo o rango de fechas, **When** ADMIN solicita el balance de comprobación, **Then** recibe por cuenta los saldos iniciales, débitos, créditos y saldos finales del rango, con totales de control.
4. **Given** que el reporte se puede consultar con filtros, **When** ADMIN lo exporta a CSV o XLSX conservando esos filtros, **Then** el archivo contiene los mismos registros, columnas, periodo y totales que la consulta correspondiente.
5. **Given** un asiento original y su reversión, **When** se consultan los reportes, **Then** ambos movimientos aparecen con su relación; los importes de la reversión compensan los del original sin ocultar ni borrar ninguno.
6. **Given** un usuario sin rol ADMIN, **When** consulta o exporta reportes, **Then** recibe `401` o `403` y no obtiene datos financieros.

### User Story 5 - Migrar y consultar el historial existente (Priority: P2)

El sistema incorpora catálogo y periodos sin borrar ni alterar asientos existentes. Las líneas históricas siguen consultables con sus códigos y nombres capturados, aunque no puedan vincularse automáticamente a una cuenta del catálogo.

**Why this priority**: La nueva capacidad debe ser utilizable en la base existente sin perder evidencia contable ni atribuir cuentas incorrectamente.

**Independent Test**: Aplicar la migración a una base con asientos previos; comparar identificadores, líneas, montos, fechas, estado, responsables y relaciones antes y después; consultar un reporte que incluya tanto líneas vinculadas como históricas no vinculadas.

**Acceptance Scenarios**:

1. **Given** asientos creados antes del catálogo, **When** se actualiza el esquema, **Then** se conservan sus IDs, datos, snapshots, responsables, eventos y relaciones.
2. **Given** una línea cuyo texto coincide con una cuenta nueva, **When** ocurre la migración, **Then** no se asigna automáticamente por coincidencia textual; el dato se mantiene como histórico sin vínculo.
3. **Given** que la migración se ejecuta más de una vez según el mecanismo versionado del proyecto, **When** se aplica un cambio ya registrado, **Then** no duplica planes, cuentas, periodos ni altera datos existentes.

### Edge Cases

- La carga del PCGE Modificado 2019 debe verificarse contra la fuente MEF y dejar edicion, fuente y vigencia visibles; no debe presentarse como certificacion tributaria.
- Dos ADMIN intentan cambiar simultáneamente el plan predeterminado: solo una transición puede quedar vigente y debe quedar auditada.
- Una cuenta padre que tenga cuentas hijas no debe aceptar movimientos; no se permiten ciclos ni códigos duplicados dentro de una misma versión del plan.
- Una cuenta usada por asientos confirmados no se elimina físicamente; se conserva para consulta aunque esté inactiva o fuera de vigencia.
- Un periodo con asientos no debe poder eliminarse; la reapertura requiere motivo y no borra el cierre anterior.
- Una reversión debe contabilizarse en un periodo abierto; si el periodo original está cerrado, no debe reabrirse automáticamente.
- Los filtros de fechas deben ser inclusivos y validar que inicio no sea posterior al fin.
- Los reportes que incluyan asientos revertidos deben mostrar el original y la reversión de forma transparente, y calcular ambos movimientos una sola vez.
- El balance debe seguir equilibrado para el mismo conjunto contable; si existen líneas históricas sin vínculo de catálogo, se incluyen usando su código y nombre snapshot.
- Exportaciones grandes deben admitir paginación o límites definidos y nunca omitir silenciosamente filas.
- Errores de validación, permisos, filtros o estado no deben revelar consultas, credenciales ni datos no autorizados.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El backend debe permitir únicamente a cuentas autenticadas con rol `ADMIN` consultar o administrar planes, cuentas, periodos y reportes contables. Las demás cuentas reciben `403`; una sesión ausente o inválida recibe `401`.
- **FR-002**: El sistema debe ofrecer un plan contable peruano PCGE como plan predeterminado inicial. Cada plan debe identificar nombre, jurisdicción, edición, fuente, fechas de vigencia y estado; el producto no debe afirmar que el catálogo cumple obligaciones tributarias o PLE por estar disponible.
- **FR-003**: Un ADMIN debe poder crear planes contables alternativos y cuentas organizadas jerárquicamente, indicando como mínimo código, denominación, cuenta padre opcional, naturaleza/saldo normal, vigencia y estado.
- **FR-004**: El sistema debe distinguir cuentas de agrupación de cuentas imputables. Solo cuentas activas, vigentes e imputables pueden asociarse a nuevas líneas contables; una cuenta con descendientes no puede ser imputable mientras existan esos descendientes.
- **FR-005**: El sistema debe impedir códigos duplicados dentro de una misma edición del plan, referencias a padres de otro plan, ciclos jerárquicos y eliminación física de cuentas referenciadas. La desactivación o nueva edición debe preservar su historia.
- **FR-006**: El backend debe permitir consultar planes, el plan predeterminado y las cuentas por jerarquía, código, denominación, estado y condición imputable, con paginación cuando corresponda.
- **FR-007**: Un ADMIN debe poder seleccionar el plan predeterminado para nuevas operaciones. El PCGE peruano queda seleccionado al inicio; cambiarlo requiere una acción explícita auditada y no cambia planes ni líneas históricas.
- **FR-008**: Cada línea de asiento nuevo debe referenciar una cuenta imputable del plan seleccionado. El asiento debe conservar el identificador/versionado de cuenta junto con código y denominación snapshot aplicados al confirmar; ningún cambio posterior al catálogo debe alterar asientos confirmados.
- **FR-009**: Las líneas existentes antes de activar el catálogo deben conservar todos sus campos y funcionar sin asignación de cuenta automática. Los reportes deben incluirlas mediante sus valores históricos de código y denominación.
- **FR-010**: El sistema debe gestionar periodos contables por mes calendario, identificados por año y mes, con estados abierto/cerrado. No debe permitir crear o revertir asientos cuya fecha de operación pertenece a un periodo cerrado.
- **FR-011**: Cerrar o reabrir un periodo debe registrar actor ADMIN, fecha y hora, estado anterior y nuevo; reabrir debe exigir un motivo. El historial de transiciones no puede sobrescribirse ni eliminarse.
- **FR-012**: El sistema debe ofrecer tres consultas: diario de movimientos, mayor por cuenta y balance de comprobación. Todas deben aceptar periodo o rango de fechas y respetar filtros de cuenta y estado aplicables.
- **FR-013**: El diario debe presentar correlativo, fecha de operación, concepto, cuenta, código y denominación, debe, haber, total y referencias de reversión; debe conservar el orden determinista por fecha y correlativo.
- **FR-014**: El mayor debe presentar saldo inicial, movimientos de debe/haber, saldo acumulado y referencia a cada asiento para una cuenta durante el rango consultado.
- **FR-015**: El balance de comprobación debe presentar por cuenta los saldos iniciales, débitos, créditos y saldos finales del rango, así como totales de debe y haber para conciliación. Los asientos y reversiones cuentan cada uno una vez.
- **FR-016**: Cada uno de los tres reportes debe poder exportarse a CSV y XLSX con las mismas columnas, filtros, periodo, orden y totales que la consulta equivalente. La respuesta debe identificar el formato y periodo exportado y no truncar filas sin aviso.
- **FR-017**: Las consultas y exportaciones deben devolver paginación o límites explícitos, aplicar filtros de fecha inclusivos, y rechazar rangos inválidos antes de producir resultados.
- **FR-018**: El backend debe mantener consistentes los reportes con los asientos confirmados y sus reversiones; una reversión se muestra junto al asiento original sin ocultar o sobrescribirlo.
- **FR-019**: Las escrituras de planes, cuentas, selección de plan, periodos y transiciones deben conservar actor, fecha y datos de auditoría necesarios; los datos financieros no se deben exponer a roles sin permiso.
- **FR-020**: El backend debe permitir a ADMIN consultar el historial auditable de cambios de planes/cuentas y transiciones de periodos, paginado y filtrado por entidad y fecha.
- **FR-021**: Cada operación descrita para consultar o administrar planes/cuentas, selección del plan vigente, periodos, reportes y descargas debe tener entradas, resultados, filtros, permisos y errores definidos de forma verificable.
- **FR-022**: La migración de esquema debe ser versionada, segura para datos existentes y repetible mediante el mecanismo de migraciones del proyecto. Debe conservar IDs, importes, fechas, líneas, snapshots, estados, responsables, auditoría y vínculos de reversión; no debe mapear cuentas históricas por coincidencia de texto.
- **FR-023**: Los registros nuevos y reportes de esta función son contabilidad interna en PEN. No se genera ni presenta PLE, no se calculan obligaciones tributarias, no hay conversión de moneda ni contabilización automática de pagos, compras o ventas.

### Key Entities *(include if feature involves data)*

- **Plan contable**: Conjunto versionado de cuentas para una jurisdicción, con fuente, vigencia, estado y condición de plan predeterminado.
- **Cuenta contable**: Nodo del plan con código, nombre, jerarquía, naturaleza, vigencia, estado y elegibilidad para recibir movimientos.
- **Línea contable**: Movimiento de debe o haber de un asiento; vincula una cuenta cuando proviene del catálogo y conserva el snapshot histórico de código y nombre.
- **Periodo contable**: Mes calendario con estado abierto o cerrado y eventos auditados de cada transición.
- **Reporte contable**: Vista filtrada del diario, mayor o balance de comprobación derivada de los asientos y reversiones del rango solicitado.
- **Evento de auditoría**: Registro inmutable de cambios a planes, cuentas, plan predeterminado y periodos, con actor y momento.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de nuevas líneas de asientos se vincula a una cuenta activa, imputable y del plan seleccionado; las líneas anteriores permanecen consultables sin cambios.
- **SC-002**: Un ADMIN puede localizar una cuenta por código o nombre y revisar su posición jerárquica en menos de 10 segundos en una consulta estándar.
- **SC-003**: El 100% de intentos de registrar o revertir asientos en periodos cerrados se rechazan sin cambios persistentes.
- **SC-004**: Cada cierre y reapertura queda asociado al actor y momento correctos; el 100% de reaperturas conserva un motivo auditable.
- **SC-005**: Para un mismo periodo y filtros, los resultados CSV y XLSX coinciden con el reporte consultado en filas, importes y totales.
- **SC-006**: En todos los reportes de prueba, los débitos y créditos del mismo conjunto de asientos balanceados concilian y las reversiones compensan el original sin duplicación u omisión.
- **SC-007**: El 100% de consultas y exportaciones de usuarios que no sean ADMIN son rechazadas sin entregar datos contables.
- **SC-008**: Después de la migración, el 100% de identificadores, valores, fechas, líneas, responsables y relaciones de asientos previos se conserva sin mapeo automático de cuentas.

## Assumptions

- El rol autorizado continúa siendo `ADMIN`; la autenticación existente se conserva.
- El plan PCGE peruano es el predeterminado inicial. La versión inicial es el PCGE Modificado 2019 publicado por el MEF; la importación debe verificarse contra la fuente oficial antes de activarse. Su carga no significa certificación tributaria.
- Los planes alternativos pueden existir simultáneamente, pero solo uno se selecciona como predeterminado para nuevas líneas. Cambiar el predeterminado no afecta asientos confirmados.
- Los periodos son meses calendario y no se pueden borrar si tienen historial; un periodo cerrado solo vuelve a abrirse por decisión explícita ADMIN con motivo.
- Los asientos existentes son inmutables y se consultan con los snapshots que ya guardan; no se intentará reconstruir su cuenta de catálogo con heurísticas.
- La moneda sigue siendo PEN, como en la función contable existente. No se incorporan conversión o tratamiento multimoneda.
- Los reportes son herramientas internas de consulta y control, no libros electrónicos PLE ni declaraciones a SUNAT. Su formato no se presenta como cumplimiento normativo.
- La función no automatiza asientos a partir de pagos, compras o ventas; cada asiento continúa registrándose mediante el flujo contable autorizado.
- El alcance es exclusivamente backend y contratos. La interfaz frontend tendrá una especificación separada.
- Las rutas existentes de categorías, asientos, detalle y reversión se conservan, sujetas a la validación adicional de cuentas del catálogo y periodos abiertos.

## Existing, Changed, and New Scope

- **Existe hoy**: categorías contables; creación confirmada e inmutable de asientos balanceados; líneas con código y nombre de cuenta en texto; listado, detalle y reversión; autorización ADMIN y auditoría de operaciones.
- **Debe modificarse**: captura de líneas nuevas para elegir cuentas del plan; validación de periodo abierto; contratos de lectura de líneas para incluir vínculo y snapshot; consultas de asientos para mostrar tanto líneas históricas no vinculadas como nuevas vinculadas.
- **Es nuevo**: plan PCGE peruano versionado predeterminado; creación/consulta de planes alternativos y cuentas; selección auditada del plan predeterminado; periodos mensuales con cierre/reapertura auditados; diario, mayor y balance de comprobación con exportación CSV/XLSX; migración compatible para esquema existente.

## Scope Boundaries

- No generación, firma, validación ni presentación de PLE o libros electrónicos SUNAT.
- No certificación del PCGE cargado ni asesoría sobre régimen u obligaciones tributarias.
- No contabilización automática, conciliación bancaria, gestión de impuestos, multimoneda ni generación de estados financieros completos.
- No cambios de interfaz en el repositorio frontend.



