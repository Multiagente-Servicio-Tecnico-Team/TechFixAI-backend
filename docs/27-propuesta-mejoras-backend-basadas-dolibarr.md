# Propuesta de mejoras del backend inspiradas en Dolibarr

**Estado:** análisis y recomendaciones; no es una especificación aprobada ni una implementación.
**Fecha de revisión:** 2026-11-08.

## Objetivo y alcance

Comparar capacidades útiles del código local de Dolibarr con el backend TechFix.AI y proponer mejoras para un taller que también gestiona ventas e inventario. La propuesta se limita al backend; las pantallas deben especificarse después en el repositorio del frontend.

La revisión se basó en el código actual de `app/`, las rutas FastAPI y el esquema documentado en `sql/esquema-vacio-produccion.sql`. No se inspeccionó una base de datos remota en esta tarea. La guía de Dolibarr está en `../dolibarr/TECHFIXAI-ERP-REFERENCE.md`; tener una función en ese código no implica que esté habilitada en una instalación.

## Capacidades que ya existen en TechFix.AI

Estas funciones no deberían replantearse como si faltaran:

| Área | Estado observado | Referencias del backend |
| --- | --- | --- |
| Cuentas y clientes | `users` y `customers` separados; los clientes pueden asociarse a una cuenta, y hay auditoría de cambios | `app/adapters/api/customers.py`, `app/adapters/persistence/customers.py`, `customers`, `customer_audit_events` |
| Tickets de servicio | Administración de tickets, cliente manual o vinculado, creación de cotizaciones de servicio y auditoría | `app/adapters/api/admin_tickets.py`, `app/adapters/persistence/admin_tickets.py`, `tickets`, `ticket_audit_events` |
| Cotizaciones de venta | Cotizaciones, aceptación, confirmación de pago, pedidos de venta, reservas y movimientos de salida; el cliente consulta sus propios registros | `app/adapters/api/sales_quotes.py`, `app/adapters/persistence/sales_quotes.py`, `quotes`, `sales_orders`, `payments` |
| Compras recibidas | Proveedores, registro de comprobantes, recepciones parciales/completas, auditoría y entradas de inventario | `app/adapters/api/purchases.py`, `app/adapters/persistence/purchases.py`, `supplier_purchases`, `purchase_receipts` |
| Inventario | Catálogo CRUD y categorías; hay movimientos para recepción de compra y venta | `app/adapters/api/inventory.py`, `app/adapters/persistence/inventory.py`, `inventory_movements` |
| Contabilidad interna | Asientos balanceados en PEN, líneas de debe/haber, categorías, consulta, reversión y auditoría; solo ADMIN | `app/adapters/api/accounting.py`, `app/domain/accounting.py`, `accounting_entries`, `accounting_entry_lines` |

La contabilidad actual es un registro interno. No integra automáticamente los pagos/compras, no ofrece un catálogo contable seleccionable ni acredita por sí sola cumplimiento tributario peruano o PLE.

## Brechas verificadas y mejoras recomendadas

### P0 — Hacer que toda variación de stock deje movimiento

**Hallazgo:** `PUT /api/inventory/parts/{code}` permite actualizar `current_stock` en el mismo flujo que edita nombre, precio y categoría (`app/adapters/persistence/inventory.py`). Sin embargo, el esquema solo acepta movimientos `PURCHASE_RECEIPT` y `SALE`, con referencia obligatoria al documento de origen. Un ajuste manual puede cambiar el saldo sin dejar un movimiento en `inventory_movements`.

**Inspiración:** Dolibarr conserva movimientos en `llx_stock_mouvement` en lugar de tratar el saldo como toda la historia del inventario.

**Propuesta:** hacer que el CRUD del artículo no permita editar el saldo. Agregar una operación administrativa explícita de ajuste que guarde cantidad anterior y nueva, diferencia, motivo, actor, fecha y referencia opcional; actualizar saldo y movimiento en una misma transacción, con control de idempotencia. Agregar tipos de movimiento para ajuste positivo/negativo y definir cómo corregir un ajuste erróneo con otro movimiento compensatorio.

**Criterio de aceptación sugerido:** no puede cambiar el stock por edición común del artículo; cada ajuste autorizado produce exactamente un movimiento; no se permiten existencias negativas ni reintentos duplicados; los saldos calculados desde movimientos se pueden conciliar con el saldo materializado.

### P0 — Exponer el ciclo de órdenes de compra que ya aparece en el esquema

**Hallazgo:** existen `purchase_orders` y `purchase_order_items`, y `supplier_purchases.purchase_order_id` permite asociarles un comprobante. La ruta de compras valida que la orden exista y corresponda al proveedor, pero no se encontraron rutas para crear, listar, consultar o cambiar el estado de esas órdenes.

**Inspiración:** Dolibarr separa la solicitud/pedido al proveedor, recepción física, factura del proveedor y pago.

**Propuesta:** definir y exponer endpoints ADMIN para crear/listar/detallar órdenes, administrar sus líneas, validar/enviar/cancelar y consultar cantidades pedidas y recibidas. Al recibir mercancía, mantener la recepción como operación separada e impedir recepciones superiores a lo pendiente. Mantener la compra/comprobante existente como entidad distinta. Registrar actor y transiciones.

**Criterio de aceptación sugerido:** una orden no modifica stock; una recepción sí crea entrada trazable; el comprobante recibido puede relacionarse con una orden sin reemplazarla; una orden cancelada o recibida completamente no acepta transiciones incompatibles.

### P1 — Agregar órdenes de trabajo/intervenciones para reparaciones

**Hallazgo:** el backend contiene tickets y cotizaciones de servicio, pero no una entidad/ruta específica de intervención u orden de trabajo para registrar ejecución técnica, técnico asignado, tiempos, pasos y repuestos usados. El esquema sí tiene movimientos de stock y garantías, pero no un objeto de trabajo de taller conectado al ticket.

**Inspiración:** Dolibarr mantiene tickets e intervenciones (`fichinter`) como objetos separados; la intervención puede tener líneas/tiempo y estado propio.

**Propuesta:** modelar una orden de trabajo asociada a un ticket, con técnico responsable, estado, fechas, diagnóstico de ejecución, tareas/observaciones y líneas de mano de obra/repuestos consumidos. Cada repuesto consumido debe generar movimiento `SERVICE_CONSUMPTION` vinculado a la línea de trabajo. Mantener la cotización como autorización económica y la orden de trabajo como ejecución, sin duplicar los datos originales del cliente.

**Criterio de aceptación sugerido:** el ticket puede avanzar a trabajo solo cuando corresponde; las piezas consumidas no se descuentan dos veces; se conserva quién ejecutó cada acción y cuándo; el historial del ticket muestra cotización y ejecución por separado.

### P1 — Catálogo de cuentas y consultas contables

**Hallazgo:** las líneas de `accounting_entry_lines` guardan `account_code` y `account_name` como valores escritos en cada asiento. Hay categorías operativas, pero no se encontró catálogo de cuentas, selección de plan, periodos fiscales ni reportes contables agregados en la API.

**Inspiración:** Dolibarr permite seleccionar/cargar un modelo de plan contable por país, administrar cuentas y generar balance, mayor y exportación contable. En la copia local revisada no está el archivo de plan `llx_accounting_account_pe.sql`; esto tampoco demuestra adaptación SUNAT.

**Propuesta:** después de validar el plan con un contador, añadir entidades para plan/cuenta y vigencia, con códigos, nombres, jerarquía, naturaleza y estado. Seleccionar la cuenta desde el catálogo al crear líneas. Conservar código/nombre como snapshot en asientos ya confirmados para que renombrar una cuenta no altere el historial. Añadir periodos contables/cierre y consultas de diario, mayor y balance de comprobación.

**Límite recomendado:** empezar con contabilidad interna, exportación CSV/XLSX y reportes de control. Dejar PLE y presentación electrónica fuera hasta validar régimen, catálogo y formatos con un contador. No contabilizar pagos automáticamente sin una política contable explícita y pruebas de conciliación.


**Estado de TechFix.AI (2026-11-09):** se implementaron en el backend el catálogo ADMIN, periodos mensuales y consultas de diario, mayor y balance con exportación CSV/XLSX. Las migraciones 012/013 quedaron aplicadas y registradas en el ledger de la base de prueba `multiagentedb`. El saldo normal de las cuentas es una clasificación inicial inferida y requiere revisión contable. Los triggers de inmutabilidad para asientos y líneas permanecen deshabilitados en esa base según la solicitud temporal previa del usuario.

### P1 — Generar documentos descargables desde registros confirmados

**Hallazgo:** no se encontró en `app/` un módulo de generación de documentos PDF/ODT ni rutas de descarga de comprobantes, cotizaciones o informes.

**Inspiración:** Dolibarr ofrece plantillas seleccionables de PDF/ODT para propuestas, pedidos, facturas, intervenciones e inventario, generadas desde sus objetos registrados.

**Propuesta:** comenzar con PDF de cotización de venta, cotización de servicio y constancia de recepción de compra. El documento debe derivarse de una consulta consistente del registro y conservar referencia, fecha, cliente/proveedor, líneas, cantidades, importes, impuestos, estado y autor. Guardar metadatos del artefacto (tipo, objeto, versión de plantilla, fecha y hash); proteger la descarga con los mismos permisos y titularidad del objeto.

**Criterio de aceptación sugerido:** el PDF coincide con los importes persistidos, no permite cambiar el contenido del registro, una descarga cliente solo expone sus documentos, y una nueva versión de plantilla no altera documentos ya emitidos.

### P2 — Informes operativos con filtros y agregación en backend

**Hallazgo:** hay endpoints transaccionales para listar compras, pedidos, pagos, tickets e inventario, pero no se encontraron endpoints dedicados a reportes gerenciales.

**Inspiración:** Dolibarr tiene estadísticas por propuestas, facturas, terceros, pedidos, compras, productos y proveedores, además de reportes contables.

**Propuesta:** endpoints de lectura con filtros por periodo y permisos para: volumen de tickets por estado/tipo y tiempo de resolución; conversión de cotizaciones a pedidos; ventas/pagos recibidos y pendientes; compras por proveedor; existencias bajo mínimo, valoración simple y movimientos; garantías próximas a vencer. Definir primero las fórmulas y la moneda; no inferir ingresos desde cotizaciones pendientes ni contar una orden como venta pagada.

**Criterio de aceptación sugerido:** cada total tiene definición documentada, los filtros coinciden con los listados de origen, se pagina o agrega en SQL sin descargar tablas completas, y datos de clientes no se exponen a roles no autorizados.

### P2 — Adjuntar evidencia a tickets, compras y garantías

**Hallazgo:** en el esquema revisado no se observó un catálogo común de documentos adjuntos asociado a tickets/órdenes de trabajo/compras/garantías.

**Propuesta:** metadatos de archivo vinculados a objeto, usuario que lo sube, fecha, tipo MIME, tamaño, hash y visibilidad. Guardar binarios en almacenamiento privado; entregar archivos por URL/ruta autorizada temporal, no por directorio público. Limitar extensiones, tamaño, análisis de contenido y acceso por rol/titularidad.

**Aplicación práctica:** fotos de recepción y daño, evidencia diagnóstica, autorizaciones, comprobantes y documentos de garantía.

## Orden de implementación sugerido

1. **Control de stock:** impedir ajustes silenciosos y añadir movimientos manuales auditables. Evita discrepancias inmediatas entre cantidad y ledger.
2. **Órdenes de compra:** completar la parte que la base ya modela y conectar pedido, recepción y comprobante.
3. **Órdenes de trabajo:** formalizar la ejecución del servicio técnico y el consumo de repuestos.
4. **Contabilidad configurable:** catálogo validado por contador, periodos y reportes internos; conservar el alcance sin PLE por ahora.
5. **PDF y reportes operativos:** cuando los contratos de cotización/orden/recepción sean estables.
6. **Adjuntos y evidencias:** definir almacenamiento privado y políticas antes de habilitar carga de archivos.

## Decisiones que requieren validación de negocio

No se resuelven por copiar el código de Dolibarr:

- Qué estados y aprobaciones requiere una orden de compra; quién puede aprobarla y si se necesita comparación de proveedores.
- Qué pasos, evidencia y firmas forman una orden de trabajo de reparación.
- Qué plan contable debe utilizar la empresa, quién lo valida y qué informes necesita el contador.
- Qué documentos se consideran emitidos/inmutables y qué información debe aparecer en PDF.
- Cuánto tiempo se conservan adjuntos y quién puede ver fotografías o comprobantes.

## Referencias revisadas

- Dolibarr: `../dolibarr/TECHFIXAI-ERP-REFERENCE.md`; `dolibarr/htdocs/product/stock/class/mouvementstock.class.php`; `dolibarr/htdocs/fourn/class/fournisseur.commande.class.php`; `dolibarr/htdocs/fichinter/class/fichinter.class.php`; `dolibarr/htdocs/accountancy/admin/account.php`; `dolibarr/htdocs/accountancy/class/accountancyreport.class.php`; `dolibarr/htdocs/core/modules/propale/doc/` y `facture/doc/`.
- TechFix.AI: `app/adapters/api/inventory.py`, `app/adapters/persistence/inventory.py`, `app/adapters/api/purchases.py`, `app/adapters/persistence/purchases.py`, `app/adapters/api/sales_quotes.py`, `app/adapters/api/accounting.py`, `app/adapters/api/admin_tickets.py`, `sql/esquema-vacio-produccion.sql`.
- Especificaciones relacionadas: `specs/003-asientos-contables/`, `specs/004-gestion-admin-tickets/`, `specs/005-api-inventario/`, `specs/006-registro-compras-proveedores/`, `specs/007-gestion-clientes-comerciales/`.
