# Implementation Plan: Asistente contable común

**Branch**: descentralizado-sprint2 | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

## Summary

Diseñar una interfaz conversacional exclusiva para ADMIN sobre las operaciones ya definidas por [003](../003-asientos-contables/spec.md): consultar categorías, listar asientos, consultar detalle, crear un asiento confirmado y solicitar reversión con motivo. ADMIN proporciona los datos y las líneas; el asistente los valida con el dominio de 003 y muestra una vista previa temporal. El chat devuelve una vista previa contable estructurada y temporal. Al pulsar Confirmar, el frontend envía los datos revisados directamente al POST existente de 003 con su Idempotency-Key; ese backend vuelve a validar ADMIN y el balance y crea el asiento confirmado. No se añade una acción contable a POST /api/chat. La capacidad y sus reglas son compartidas; cada patrón conserva su coordinación.

Este plan no añade endpoints contables, tablas, migraciones, servicios paralelos ni reglas para derivar asientos de ventas, compras, pagos, cotizaciones, reembolsos o inventario. Solo se crea este archivo; la implementación y la coordinación de contrato quedan para una etapa posterior.

## Technical Context

- **Backend**: Python, FastAPI y LangGraph; arquitectura domain/application/adapters/infrastructure existente.
- **Autoridad contable**: app/domain/accounting.py, app/application/accounting.py, app/adapters/api/accounting.py y app/adapters/persistence/accounting.py.
- **Autorización**: sesión firmada y verificación ADMIN en app/accounts/session.py; composición actual en app/infrastructure/chat_app.py.
- **Contratos**: [OpenAPI de 003](../003-asientos-contables/contracts/accounting.openapi.yaml) para las operaciones contables; app/chat/contract.py para el chat común.
- **Persistencia**: exclusivamente el repositorio y las tablas de 003 para asientos confirmados y reversiones. La vista previa no es una entidad persistida ni un estado DRAFT.
- **Pruebas previstas**: unitarias de validación y secuencia de confirmación, contratos de API/chat y escenarios equivalentes para los tres patrones; integración PostgreSQL real solo en un entorno de prueba autorizado.

## Constitution Check

La [constitución](../../.specify/memory/constitution.md) sigue siendo una plantilla sin principios ratificados ni reglas concretas. Se aplican AGENTS.md y las decisiones de 001, 003 y 006. La revisión antes y después del diseño debe comprobar:

- **Acceso**: solo ADMIN, comprobado por backend antes de consultar o escribir; CUSTOMER y TECHNICIAN rechazados.
- **Reglas compartidas**: misma autorización, validación y resultado en los tres patrones; distinta coordinación según 001.
- **Contabilidad manual**: D1/D2 de 003 intactas; ninguna operación comercial origina un asiento y la creación queda confirmada en una transacción.
- **Exactitud y privacidad**: Decimal/PEN; no registrar mensajes completos, credenciales ni textos de excepciones en trazas.
- **Compatibilidad**: 006 mantiene compra, pago y recepción separados y sin contabilización automática; no hay cambios de esquema ni rutas.

## Diseño de la capacidad compartida

### Operaciones reutilizadas de 003

| Intención de ADMIN | Operación existente | Control del asistente |
| --- | --- | --- |
| Consultar categorías | GET /api/admin/accounting/categories | Mostrar categorías activas reales; no inventar valores. |
| Listar asientos | GET /api/admin/accounting/entries | Aplicar únicamente paginación y filtros admitidos por 003. |
| Consultar detalle | GET /api/admin/accounting/entries/{entry_id} | Mostrar encabezado, líneas, estado e historial que devuelva 003. |
| Crear asiento | POST /api/admin/accounting/entries | Frontend envía el payload revisado tras Confirmar, con Idempotency-Key UUID; 003 revalida ADMIN y balance y crea CONFIRMED. |
| Solicitar reversión | POST /api/admin/accounting/entries/{entry_id}/reverse | Exigir identificador, fecha y motivo; conservar la semántica de reversión e idempotencia de 003. |

El adaptador conversacional reutiliza consultas y validación compartidas sin acceder directamente a persistencia. Para crear, el frontend invoca el POST existente de 003 con la cookie de sesión y el payload revisado; el agente no llama a create_entry ni a una ruta alternativa. Las rutas de 003 son la única superficie HTTP contable. La reversión conserva la operación existente de 003; su interacción exacta con frontend se coordina sin añadir una ruta.

### Ingreso, vista previa y confirmación

1. Verificar sesión ADMIN antes de cualquier operación contable en el chat. La identidad procede de la sesión, nunca del texto o cuerpo enviado.
2. Recoger solo los datos que ADMIN aporte: fecha de operación, concepto, detalle, categoría y líneas con código, denominación, descripción opcional y debe/haber. Consultar categorías existentes de 003 cuando haga falta.
3. Validar con las reglas deterministas de app/domain/accounting.py: 2–100 líneas, importes Decimal/PEN, un importe positivo en exactamente un lado por línea y totales iguales. La vista previa no reemplaza la validación de la API.
4. Devolver en la respuesta de POST /api/chat una vista previa contable estructurada, distinguible de QuoteOut, con los campos ingresados, totales calculados, moneda PEN y estado de validación. Es temporal: no se persiste como asiento ni como DRAFT y no recibe correlativo. Si faltan datos, pedirlos; no inferir cuentas, importes, IGV o costos.
5. El frontend muestra la vista previa a ADMIN y retiene temporalmente sus datos. Al pulsar Confirmar, llama directamente a POST /api/admin/accounting/entries con el payload revisado exactamente según el OpenAPI de 003 y una Idempotency-Key UUID estable para ese intento. No se añade una acción de confirmación a POST /api/chat.
6. El backend de 003 vuelve a verificar la sesión ADMIN, la categoría y el balance; solo un POST aceptado crea el asiento CONFIRMED en una operación y registra el responsable y la auditoría de 003. La respuesta 201 es el asiento creado; un reintento con la misma clave y payload devuelve el resultado según 003. Si el payload cambia, la confirmación anterior no lo cubre y la clave no puede reutilizarse con otro contenido.

**Estado temporal**: el chat no guarda un borrador contable en tablas nuevas ni en el checkpointer del grafo. El frontend conserva los datos de la vista previa solo durante la interacción y los envía directamente al POST de 003 al confirmar. La duración, limpieza y tratamiento de recarga de la interfaz deben coordinarse con frontend; la API 003 no almacena la vista previa. La protección real de la escritura no depende de la vista previa: la API revalida permisos y contenido.

### Reversión y consultas

Consultas y filtros se delegan a AccountingService sin transformar su semántica. La reversión es una intención separada de la creación: ADMIN indica asiento, fecha y motivo, revisa la operación y confirma; el backend usa reverse_entry de 003. No editar ni borrar un asiento CONFIRMED. Los errores de 003 se traducen al contrato de chat sin afirmar que hubo escritura.

## Integración por patrón

| Patrón | Trabajo de integración | Límite |
| --- | --- | --- |
| Descentralizado, en este worktree | Conectar la capacidad compartida al enrutamiento y handoffs existentes, con verificación ADMIN antes de toda operación; preservar estado, ownership, locks, recuperación y los nueve roles actuales. | No agregar nodos alias duplicados ni guardar el contenido contable como checkpoint duradero. |
| Orquestador | Coordinar con su responsable el punto de delegación desde el supervisor a la misma capacidad y sus pruebas de contrato. | No modificar su código desde este worktree ni convertir el contador en supervisor global. |
| Jerárquico | Coordinar con su responsable la delegación desde la jerarquía a la misma capacidad y sus pruebas de contrato. | No modificar su código desde este worktree ni cambiar sus políticas de coordinación. |

La lógica común de autorización, validación y acceso a 003 se comparte; solo el enrutamiento y la presentación conversacional pertenecen a cada patrón. La comparación de 001 exige los mismos resultados y efectos para la misma operación ADMIN.

## Contrato a coordinar con frontend

El [contrato actual de chat](../../app/chat/contract.py) devuelve reply, quote y ticket, pero no una vista previa contable estructurada. La ampliación necesaria es solo una salida opcional y compatible de POST /api/chat para ADMIN; no se añade una acción de confirmación al chat ni una ruta contable:

- incluir en la respuesta una vista previa contable estructurada con fecha, concepto, detalle, categoría, moneda PEN, líneas, totales y validación; distinguirla de QuoteOut y de un asiento CONFIRMED;
- mostrarla solo a ADMIN y no registrar su contenido en trazas; no presentarla como persistida ni asignarle correlativo;
- coordinar cómo el frontend retiene temporalmente el payload revisado, muestra el botón Confirmar y envía POST /api/admin/accounting/entries con cookie de sesión, cuerpo CreateAccountingEntry e Idempotency-Key del [OpenAPI de 003](../003-asientos-contables/contracts/accounting.openapi.yaml);
- manejar 201 como creación, 200 como repetición idempotente, y 401/403/409/422/503 sin afirmar éxito cuando 003 rechaza la operación;
- después del POST, mostrar el asiento confirmado usando la respuesta real de 003; no inferirlo del estado del chat.

**Coordinación pendiente con frontend**: acordar el nombre y esquema del campo opcional de vista previa en ChatOut, la política de conservación temporal, el botón Confirmar, el envío de credenciales y la reutilización de la misma Idempotency-Key en reintentos. No se implementa frontend ni se contacta al equipo en esta etapa. El contrato actual permite este flujo mediante una ampliación de salida de chat y el POST contable existente; no necesita una acción de confirmación en ChatIn ni una ruta nueva.

## Validación planificada

1. Revisión estática de imports, rutas y composición: ninguna API o migración contable nueva, ningún acceso de patrones a persistencia directa y ninguna ruta que eluda ADMIN.
2. Pruebas unitarias aisladas con repositorio falso: extracción de datos manuales, validación de 003, vista previa sin persistencia, rechazo de CUSTOMER/TECHNICIAN y reversión con motivo. La creación se comprueba por separado en la API 003 tras el POST del frontend.
3. Pruebas de contrato para las operaciones de 003 y la salida opcional de vista previa de chat; comprobar que no existe acción contable de confirmación en ChatIn y que el POST de 003 revalida permisos y balance. Repetir resultados equivalentes en los tres patrones.
4. Pruebas de integración con base de prueba PostgreSQL, solo cuando estén disponibles y autorizadas: identidad de sesión, transacción confirmada, auditoría, idempotencia/reintentos y reversión. No declarar durabilidad PostgreSQL validada a partir de sustituciones.
5. Regresión de 001 y 006: coordinación propia de cada patrón, nueve roles actuales en Descentralizado, compras/recepción sin asiento automático y flujos comerciales sin alteración.

## Bloqueos y decisiones de coordinación

- Coordinar con frontend el campo estructurado de vista previa en ChatOut, su conservación temporal y el botón Confirmar que llama directamente al POST existente de 003. No requiere una acción nueva de ChatIn.
- Acordar la presentación de respuestas 201/200 y errores de 003, junto con la vida de la Idempotency-Key por intento; no diseñar un almacenamiento de borradores.
- Orquestador y Jerárquico requieren coordinación con sus responsables para conectar la capacidad compartida. Este plan solo describe su integración y no modifica esos patrones.
- D1 y D2 de 003 y FR-015 de 006 permanecen: ningún asiento se deriva de eventos comerciales, no hay DRAFT y cada creación válida se confirma en una operación.
