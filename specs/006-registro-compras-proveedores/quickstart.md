# Quickstart de validación: compras a proveedores

Guía para comprobar la feature después de implementar el plan. Usa únicamente una base de datos de prueba desechable/autorizada. No apuntes migraciones ni pruebas de escritura al `.env` productivo.

## Prerrequisitos

1. PostgreSQL de prueba con el esquema base ya aplicado y usuario ADMIN válido.
2. Backend configurado con variables locales documentadas en `.env.example`.
3. `sql/migrations/005_supplier_purchases.sql` revisada, respaldo disponible y destino confirmado. Aplicar la migración una sola vez con el procedimiento de despliegue local del proyecto.
4. Backend levantado con el comando habitual del README desde el repositorio.

## Validación automatizada

Desde la raíz del backend, ejecutar las suites nuevas cuando estén implementadas:

```powershell
pytest tests/unit/domain/test_purchases.py tests/unit/application/test_purchases.py
pytest tests/contract/test_purchases_api.py
pytest tests/integration/test_purchase_receipts.py
```

Resultado esperado: montos se validan con dos decimales; usuarios que no sean ADMIN reciben 403; factura duplicada responde 409; reintento de recepción con la misma clave no vuelve a incrementar el stock; una clave igual con payload distinto responde 409; error transaccional deja stock, recibo y auditoría sin cambios parciales.

## Validación funcional API

Autentícate como ADMIN y conserva la cookie de sesión del login.

1. `GET /api/admin/suppliers?active=true` devuelve proveedores activos y paginación.
2. `POST /api/admin/suppliers` crea un proveedor de prueba; `PATCH /api/admin/suppliers/{id}` permite editarlo/desactivarlo sin borrar compras relacionadas.
3. `POST /api/admin/purchases` crea un comprobante con proveedor, dos líneas, método y estado de pago. Captura el stock antes y después: deben ser iguales al registrar.
4. Repite el POST con el mismo proveedor, tipo, serie y número: debe responder 409 y conservar una única compra.
5. `GET /api/admin/purchases` filtrado por proveedor/fechas/status incluye el registro; `GET /api/admin/purchases/{id}` muestra snapshots, importes y responsable autenticado.
6. `POST /api/admin/purchases/{id}/receipts` con `Idempotency-Key` UUID y cantidades menores a la factura incrementa solamente los productos vinculados y cambia el estado a `PARTIALLY_RECEIVED`.
7. Repite idéntica petición con la misma clave: responde como replay y el stock no cambia. Reutiliza la clave con contenido diferente: responde 409.
8. Confirma la cantidad restante con una nueva clave: la compra queda `RECEIVED`; cada movimiento conserva responsable/fecha. Un concepto sin `spare_part_id` queda en el historial sin generar stock.
9. Intenta cancelar una compra ya recibida: responde 409. Cancela otra sin recepciones: deja estado `CANCELLED` y auditoría.
10. Cambia el pago de una compra `PENDING` a `PAID`; el detalle refleja el método y estado. No aparece ningún asiento contable automático.
11. Repite consultas/escrituras sin sesión y como CUSTOMER: deben recibir 401/403 y no revelar el detalle financiero.

Para las pruebas con curl o cliente HTTP, usa los cuerpos de [contracts/purchases.openapi.yaml](contracts/purchases.openapi.yaml). No guardes cookies ni credenciales en este documento ni en logs.

## Criterios de aceptación rápida

- Registrar compra no cambia existencias.
- Cada recepción aplica cantidades una sola vez, dentro de la misma transacción que guarda recibo y auditoría.
- No se modifica ni elimina físicamente una compra con efectos de inventario.
- Proveedores desactivados y repuestos posteriormente eliminados siguen identificables en el detalle histórico mediante snapshots.
- No se generan PLE, pagos parciales ni asientos contables.

## Ejecución local

Validación manual realizada el 2026-11-03 en la base de prueba `multiagentedb`:

- Se aplicó la migración `005_supplier_purchases.sql`; quedaron creadas las seis tablas nuevas y los campos de proveedor. El catálogo `spare_parts` conservó sus 431 filas.
- Recorrido API transaccional: alta de proveedor y compra, total `21.00`, duplicado `409`, dos recepciones parciales, replay idempotente `200` sin incrementar stock por segunda vez, cambio de pago a `PAID`, filtros de listado y cancelación según estado.
- La compra recibida rechazó cancelación (`409`); compra sin recepciones pudo cancelarse (`200`). La dependencia administrativa devolvió `403` cuando se configuró para denegar.
- La cantidad de asientos contables no cambió. Al finalizar, la transacción externa se revirtió: no quedaron proveedores, compras ni recibos de smoke test; el inventario volvió a sus valores anteriores y mantuvo 431 artículos.
- Se validaron compilación sintáctica de módulos Python, importación del router/composición y sintaxis YAML OpenAPI. No se ejecutó la suite automatizada del repositorio.
