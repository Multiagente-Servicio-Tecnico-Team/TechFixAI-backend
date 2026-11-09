# Migraciones SQL

Los cambios de esquema se guardan como scripts incrementales y versionados en esta carpeta. Cada migraciÃ³n se aplica una sola vez por entorno tras confirmar su estado; las partes de corte de datos deben ser seguras ante reintentos cuando sea posible. Cada script declara precondiciones, conserva datos existentes, usa transacciones cuando el motor lo permite y documenta cÃ³mo verificar su resultado y recuperarse de un fallo.

Aplicar los scripts de forma explÃ­cita al entorno seleccionado despuÃ©s de comparar su esquema real con el requisito de la migraciÃ³n. No ejecutar automÃ¡ticamente la URL de `.env` sin verificar el destino.

Los archivos `sql/esquema-vacio-produccion.sql` y `contexto/tablas postgres v2.sql` son scripts de reconstrucciÃ³n/bootstrap; no sustituyen migraciones incrementales ni deben ejecutarse para actualizar una base con datos.

## MigraciÃ³n 20261108_inventory_movement_traceability.sql

- Requiere el esquema vigente de compras, ventas, usuarios, repuestos y movimientos.
- Aplicar con escritores de stock detenidos o drenados; la migraciÃ³n bloquea `spare_parts` y `inventory_movements` mientras expande restricciones y registra el corte.
- Conserva las filas antiguas y crea una sola apertura `SYSTEM` por repuesto con saldo vigente, incluso cuando el saldo es cero. No asigna usuario humano a esa apertura.
- La migraciÃ³n estructural debe ejecutarse una sola vez. El `INSERT ... ON CONFLICT DO NOTHING` hace reintentable solo el corte por artÃ­culo si este bloque se vuelve a ejecutar tras una recuperaciÃ³n; no volver a aplicar los `ALTER TABLE` ya confirmados.
- Verificar que cada repuesto tenga apertura SYSTEM, que el valor de `stock_after` coincida con el saldo previo al corte, que la historia anterior permanezca y que la suma de saldo inicial mÃ¡s deltas posteriores concuerde con `spare_parts.current_stock`.
- En el entorno local de prueba la migraciÃ³n quedÃ³ registrada en `schema_migrations` como versiÃ³n `011`, con checksum del archivo aplicado. ProducciÃ³n y otros entornos requieren su propia aplicaciÃ³n y registro.
- Para recuperarse de un fallo, usar la atomicidad transaccional: ante error antes del `COMMIT`, PostgreSQL revierte todo. No ejecutar un rollback destructivo despuÃ©s de permitir nuevos movimientos; corregir hacia adelante con una migraciÃ³n versionada.

## Migraciones 006–011: historial reconciliado

Se restauraron los archivos versionados `006_customer_commerce_expand.sql` a `010_remove_obsolete_tables.sql` usando exactamente los bytes que coinciden con el ledger de la base de prueba. La migración de trazabilidad de inventario se denomina `011_inventory_movement_traceability.sql`; conserva los mismos bytes y checksum que el archivo que se aplicó originalmente. El preflight `python -m app.database.migrations status` confirmó las versiones 006–011 como `RECORDED`, sin desajustes.

La reconciliación de archivos no ejecutó SQL ni modificó el ledger. Las siguientes migraciones nuevas de esta característica son 012 (esquema) y 013 (catálogo PCGE).


## Migraciones 012–013: catálogo y reportes contables

- `012_accounting_catalog_schema.sql` agrega planes, cuentas, periodos y eventos append-only; los vínculos de asientos y líneas son nullable para preservar el historial. También instala los guardas de jerarquía, cuenta imputable y periodo abierto.
- `013_seed_pcge_modificado_2019.sql` carga 1192 códigos y denominaciones desde `data/accounting/pcge_modificado_2019.csv`, requiere que exista una cuenta ADMIN para la autoría del plan y selecciona PCGE Perú Modificado 2019 como predeterminado.
- Fuente del catálogo: PCGE 2019 del MEF: https://www.mef.gob.pe/contenidos/conta_publ/documentac/PCGE_2019.pdf. SHA-256 del CSV: `b723bebca0171b398284264c330077bea10524cc51ccf8897602446b4eda12a3`.
- El MEF publica códigos y denominaciones; no publica el saldo normal operativo ni la imputabilidad de esta carga. Esos dos campos se asignaron como clasificación inicial por grupo contable y debe validarlos un contador antes de registrar operaciones reales. Los códigos 89, 891 y 892 quedan sin saldo normal y no imputables.
- El usuario confirmó `multiagentedb` como la base de prueba permanente. Las migraciones 012/013 se aplicaron, verificaron y registraron en su ledger con los checksums actuales.
- El bloque de `sql/esquema-vacio-produccion.sql` contiene el mismo esquema y catálogo inicial para instalaciones nuevas. No se ejecuta como actualización de una base existente.


La base de prueba permanente confirmada por el usuario se identifica como `multiagentedb`. Al ejecutar futuras migraciones, continuar validando el ledger y no mostrar ni copiar la URL de conexión.

## Migración 014: ciclo de órdenes de compra

- La migración `014_purchase_orders_lifecycle.sql` depende del esquema vigente hasta 013 y agrega el ciclo ADMIN de borrador, emisión, cancelación y recepción física contra la orden.
- No se ha aplicado automáticamente. Antes de ejecutarla, revisar el destino, versión del esquema y estado real. El preflight detiene la migración si existe cualquier fila en `purchase_orders` o una recepción por factura asociada a una orden; no reasigna estados, líneas ni recepciones de forma automática.
- Verificación previa: confirmar el resultado de los dos chequeos del bloque `DO` usando la misma base de datos objetivo. Si el script aborta, detenerse y preparar un mapeo versionado y revisado para el historial afectado; no retirar el preflight ni borrar datos para forzar su ejecución.
- La orden no modifica existencias. Sólo una recepción física crea movimientos de inventario en la misma transacción; las recepciones por factura siguen disponibles para compras no asociadas a órdenes.
- Aplicar sólo en ventana con escritores de stock pausados y tras copia de seguridad. No ejecutar el script de esquema vacío como sustituto de esta migración. La migración no elimina órdenes, comprobantes, recepciones ni movimientos existentes.
- Después de aplicar, comprobar restricciones de origen de `inventory_movements`, relaciones entre orden/línea/recepción, auditoría, snapshots y unicidad de idempotencia. Probar en una base desechable con `PURCHASE_ORDER_TEST_DATABASE_URL`; el fixture exige que el nombre incluya `test` y nunca carga `.env`.
- El bloque SQL es transaccional. Si falla antes de `COMMIT`, PostgreSQL revierte los cambios; corregir la causa y revisar nuevamente el diff antes de reintentar. El rollback posterior a nuevas recepciones no es automático: sólo retirar columnas/tablas nuevas después de comprobar que no contengan dependencias ni historial.

## Migración 015: cotizaciones PC_BUILD independientes

- `015_pc_build_standalone_quotes.sql` permite que cotizaciones comerciales `DIRECT_SALE` y `PC_BUILD` no se relacionen con tickets de servicio; las cotizaciones `REPAIR` siguen requiriendo ticket.
- Conserva identificadores, líneas, pagos, auditoría y snapshots; solo separa las cotizaciones PC_BUILD históricas de tickets de reparación.
- Aplicada y verificada en la base local de prueba `multiagentedb`; `python -m app.database.migrations status` la muestra `RECORDED` con el checksum esperado. No implica que esté aplicada en otros entornos.

## Migración 016: auditoría de proveedores

- `016_supplier_audit_events.sql` agrega auditoría append-only a nivel de aplicación para altas y cambios de proveedores, con el ADMIN autenticado como actor.
- No modifica filas de `suppliers`; cada evento guarda los campos modificados y su fecha. La FK impide borrar el actor o proveedor mientras haya auditoría asociada.
- Aplicada y verificada en `multiagentedb`; las escrituras administrativas de proveedores requieren que la migración equivalente esté aplicada en cada entorno destino.
