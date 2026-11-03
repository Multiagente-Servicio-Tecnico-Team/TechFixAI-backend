# Research: Registro y trazabilidad de asientos contables

## Decisiones

### D1. Registrar manualmente; no inferir operaciones comerciales

- **Decisión**: Un `ADMIN` crea cada asiento a través de la API. La feature no deriva asientos desde `payments`, `quotes`, `purchase_orders`, `refunds` ni desde agentes.
- **Rationale**: El esquema comercial no representa un libro contable, algunos pagos siguen en `PENDING` y una cotización no es un ingreso recibido. Evita contabilizar como efectivo una operación que todavía no se completó.
- **Alternativas consideradas**: Generar asientos automáticamente al crear una cotización/pago —rechazada por estatus incompletos y alcance explícito—; ingerir transacciones en una fase futura, con fuentes verificadas y una especificación propia.

### D2. Un asiento se crea confirmado en una sola operación

- **Decisión**: No existe estado `DRAFT`, edición ni eliminación de asientos confirmados. Un POST exitoso crea líneas, encabezado y evento `ENTRY_CREATED` en una sola transacción.
- **Rationale**: Responde a la aclaración del usuario, reduce transiciones inconsistentes y conserva el registro original.
- **Alternativas consideradas**: Crear borradores y confirmar por separado —descartada por la respuesta explícita del usuario—; editar directamente—descartada por trazabilidad.

### D3. Corregir con una reversión completa y relacionada

- **Decisión**: Una ruta de reversión recibe fecha y razón; crea un asiento confirmado nuevo con debe/haber intercambiados, enlaza el original y marca el original `REVERSED`. Un índice único evita una segunda reversión.
- **Rationale**: Preserva la evidencia original y hace visible quién corrigió y cuándo.
- **Alternativas consideradas**: Sobrescribir/eliminar las líneas originales —descartada por inmutabilidad—; reversión parcial—se deja fuera para mantener un vínculo contable inequívoco.

### D4. Balancear debe/haber en la aplicación y en la base de datos

- **Decisión**: El dominio valida al menos dos líneas, importe positivo en exactamente uno de debe/haber y totales iguales. PostgreSQL añade restricciones por línea y una `DEFERRABLE INITIALLY DEFERRED CONSTRAINT TRIGGER` valida el total del conjunto antes del commit.
- **Rationale**: Una restricción `CHECK` ordinaria solo puede validar la fila actual y no debe usarse como una consulta de otras filas. PostgreSQL permite diferir el disparador de restricción hasta el fin de la transacción, momento en que todas las líneas ya están insertadas. Cada escritura usa un contexto transaccional SQLAlchemy que confirma en éxito y revierte al propagarse un error.
- **Alternativas consideradas**: Validar únicamente en la ruta —rechazada porque deja más caminos de escritura sin protección—; una transacción disparador inmediato —rechazada porque vería un asiento incompleto durante inserciones por línea.
- **Fuentes**: [PostgreSQL constraints](https://www.postgresql.org/docs/17/ddl-constraints.html), [PostgreSQL CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html), [SQLAlchemy 2.1 transactions](https://docs.sqlalchemy.org/en/21/core/connections.html).

### D5. Correlativo global único, no consecutivo sin huecos

- **Decisión**: Usar una secuencia global PostgreSQL para `entry_number`; la clave primaria/unique garantiza que no se repita. Los huecos causados por rollback, reintentos u operación concurrente son aceptables en este registro interno.
- **Rationale**: Es consistente con la aclaración de correlativo global sin reinicio periódico y evita bloquear una tabla contadora en cada alta.
- **Alternativas consideradas**: `MAX(entry_number) + 1` —rechazada por carreras de concurrencia—; contador sin huecos—rechazado por bloqueo y por no ser un requisito de la feature. La documentación de PostgreSQL advierte que secuencias concurrentes no son gapless y pueden consumir valores incluso si una transacción aborta.
- **Fuente**: [PostgreSQL sequence manipulation](https://www.postgresql.org/docs/16/functions-sequence.html).

### D6. Idempotencia duradera y ligada al actor

- **Decisión**: La creación exige `Idempotency-Key` UUID. La base guarda clave y hash canónico del payload con restricción única por usuario creador. Mismo actor/clave/mismo hash devuelve el recurso ya creado; mismo actor/clave/otro hash responde conflicto `409`. Para reversiones, la referencia única al asiento original proporciona idempotencia: misma fecha/razón devuelve la reversión existente y datos distintos responden conflicto.
- **Rationale**: El requisito de no duplicar asientos debe sobrevivir a reinicios del proceso y a peticiones concurrentes. La clave se almacena en la misma transacción del asiento.
- **Alternativas consideradas**: Registro solo en memoria—descartado porque se pierde al reiniciar o escalar instancias—; deduplicación por fecha/monto/concepto—descartada porque operaciones legítimas pueden coincidir.

### D7. Roles y composición

- **Decisión**: Extender `SessionGuard` con `require_admin`; montar router contable en la app compuesta existente, manteniendo la autorización en backend. Rutas: `/api/admin/accounting/categories`, `/entries`, `/entries/{entry_id}` y `/entries/{entry_id}/reverse`.
- **Rationale**: `SessionGuard.require_user` ya comprueba cookie firmada, cuenta activa y fingerprint de contraseña; el rol `ADMIN` ya protege operaciones administrativas. Las rutas existentes están dentro de `build_chat_app`, donde se comparten dependencias y manejo de errores.
- **Alternativas consideradas**: Reutilizar `require_customer`—incompatible con el rol acordado—; crear otro servidor o cuenta/rol—innecesario para la primera versión.
- **Fuente técnica**: [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/).

### D8. Categorías operativas internas y cuentas ingresadas por el personal

- **Decisión**: Crear catálogo interno de categorías, con estas claves iniciales: `SALE` (Venta), `SERVICE` (Servicio técnico), `PURCHASE` (Compra/inventario), `OPERATING_EXPENSE` (Gasto operativo), `ADJUSTMENT` (Ajuste) y `OTHER` (Otro). La reversión conserva la categoría original. Las líneas guardan código y denominación de cuenta ingresados por el `ADMIN` como snapshot.
- **Rationale**: Permite filtrar y presentar categorías sin asegurar que estas sean categorías oficiales de SUNAT. El spec no autoriza ni documenta un catálogo PCGE vigente, por lo que no se inventa ni se carga uno como oficial.
- **Alternativas consideradas**: Categoría libre—rechazada por errores de escritura y filtros fragmentados—; cargar un plan de cuentas oficial sin confirmar versión/aplicabilidad—rechazada por riesgo de datos incorrectos; integrar el plan oficial—requiere alcance y validación contable separados.

### D9. Alcance normativo y temporal

- **Decisión**: Libro interno en PEN; fecha de operación se guarda como `DATE`, marcas de auditoría en UTC. Sin campos PLE no exigidos para el registro interno y sin declarar cumplimiento tributario.
- **Rationale**: La fuente oficial de SUNAT para el Formato 5.1 incluye correlativo/código único, fecha, glosa, cuenta/código-denominación, debe, haber y totales. La obligación y los libros requeridos dependen del contribuyente; el usuario confirmó que no desea PLE en esta etapa.
- **Fuentes**: [Formato 5.1 Libro Diario de SUNAT](https://contenido.app.sunat.gob.pe/insc/Libros%2By%2BRegistros/Informacion%2Bm%C3%ADnimo%2Bformatos/FORMATO_5_1.pdf), [libros contables obligatorios](https://emprender.sunat.gob.pe/comprobantes-libros/registros-libros-electronicos/libros-registros-contables-obligatorios).

### D10. Serialización e integración

- **Decisión**: La API devuelve importes decimales como cadenas con dos decimales, fechas de operación `YYYY-MM-DD` y marcas de auditoría ISO-8601 UTC. CORS añade `Idempotency-Key` en `allow_headers`; `GET`/`POST` ya están permitidos.
- **Rationale**: Evita conversión monetaria imprecisa en JavaScript y posibilita crear idempotencia desde el futuro cliente frontend separado.
- **Alternativas consideradas**: JSON number para PEN—descartado por pérdida potencial de precisión binaria—; exponer email completo del responsable—innecesario, se devuelve identificador y nombre visible.

## Dependencias y límites conocidos

- El esquema ampliado `contexto/tablas postgres v2.sql` contiene pagos, reembolsos, compras, tickets y usuarios, pero no asientos contables, categorías contables, líneas ni eventos de auditoría.
- La tabla `users` ya contiene roles `CUSTOMER`, `TECHNICIAN`, `ADMIN`; `SessionGuard` implementa `require_user` y `require_customer`, pero no un guard administrativo reutilizable.
- `app/main.py` compone cuentas y chat; `app/infrastructure/chat_app.py` concentra la composición del router de chat. El router contable se añade a esta composición y no toca el contrato de chat.
- El frontend se encuentra en otro repositorio; este plan solo produce contrato backend/OpenAPI.
- No aplicar la migración a `.env` ni a una base desplegada durante la fase de implementación sin verificar primero el nombre/ambiente de la BD de prueba y registrar las tablas previas/posteriores.
