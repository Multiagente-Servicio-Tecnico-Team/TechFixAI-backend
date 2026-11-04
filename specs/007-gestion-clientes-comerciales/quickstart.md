# Quickstart de validación: Gestión de clientes comerciales

Este recorrido aplica después de implementar el feature. No está diseñado para ejecutarse contra producción ni ejecuta el cleanup aprobado de los ocho tickets de prueba.

## Prerrequisitos

1. Usar una base PostgreSQL aislada/restaurada desde respaldo, no la base de producción.
2. Confirmar la versión/esquema real y reconciliar las migraciones existentes; no usar el dump de reconstrucción para inferir migraciones aplicadas.
3. Tener las variables del backend configuradas en `.env`, la base aislada vacía de conexiones de otros procesos y un usuario ADMIN de prueba más dos usuarios CUSTOMER.
4. El cleanup de tickets SALE requiere un procedimiento separado con destino explícito, backup, IDs exactos y preflight. No forma parte de estos comandos.

## Comprobación automática

Desde la raíz del backend, instalar dependencias de desarrollo si la máquina aún no las tiene y ejecutar las suites específicas:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/unit/domain/test_customer_profiles.py tests/unit/domain/test_commercial_inventory_policy.py tests/unit/application/test_customer_session_resolution.py tests/unit/application/test_sales_quote_reservations.py tests/contract/test_customer_api_contract.py tests/contract/test_customer_service_ticket_contract.py tests/contract/test_sales_quote_contract.py tests/contract/test_chat_quote_reference.py -q -p no:cacheprovider
```

Las pruebas de repositorio con respuestas simuladas:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/integration/test_customer_service_ticket_repository.py tests/unit/adapters/test_repository.py tests/integration/test_refund_requests_integration.py -q -p no:cacheprovider
```

Las pruebas unitarias y de contrato disponibles pueden ejecutarse sin migrar una BD. Las pruebas de PostgreSQL requieren `CUSTOMER_COMMERCE_TEST_DATABASE_URL` y un esquema de prueba preparado; no apuntes `.env` a una BD activa que aún no tenga `customers` ni las migraciones 006–009. La prueba de concurrencia y la corrida completa de migraciones continúan pendientes hasta disponer de ese entorno. El patrón Orquestador aún no tiene flujo de venta directa, por lo que no se declara paridad de ese caso.

## Comprobación de API y escenarios

Usar las operaciones y esquemas definidos en [customer-commerce.openapi.yaml](contracts/customer-commerce.openapi.yaml) en el host local del backend.

1. ADMIN crea un customer manual sin crear `users`; listar clientes y verificar `origin=MANUAL` y `created_by_user_id`.
2. Vincular una cuenta CUSTOMER a un perfil con verificación explícita; repetir la vinculación a otro perfil debe dar conflicto.
3. Crear ticket manual para cliente manual sin cotización y verificar ticket con cero quotes y actor ADMIN.
4. Crear ticket online autenticado con cookie; incluir otro `customer_id` en el body no debe cambiar el propietario y no debe permitir acceso entre dos cuentas.
5. Crear cotización de servicio vinculada al ticket; verificar mismo customer y snapshots de precio/líneas.
6. Crear cotización de venta sin `ticket_id`; verificar que no aparece ningún ticket de taller asociado.
7. Aceptar cotizaciones concurrentes para las últimas unidades. Como máximo una reserva el total disponible; la otra devuelve conflicto y no crea aceptación/reserva parcial.
8. Verificar que cancelar/rechazar/vencer libera la reserva una sola vez y que cotización expirada ya no se acepta, aunque el worker de expiración no se haya ejecutado.
9. Confirmar pago con ADMIN y clave idempotente; el estado pasa a COMPLETED, una venta/pedido se crea, la reserva se consume, stock disminuye una sola vez y queda un movimiento SALE auditable.
10. Repetir confirmación produce el mismo resultado sin duplicar venta, pago ni movimiento. Un CUSTOMER no puede confirmar pagos ni consultar registros de otra cuenta.
11. Crear solicitud de reembolso pendiente y verificar que conserva pago/quote/cliente incluso para venta sin ticket; logística/garantía de venta referencian el pedido, mientras servicio de taller conserva ticket.

## Invariantes en PostgreSQL de prueba

- Cero tickets nuevos de tipo `SALE` por la ruta de venta directa.
- Cada customer portal está enlazado como máximo a una cuenta, y ningún cliente manual tiene credenciales.
- Cada quote de servicio tiene ticket del mismo customer; quote de venta tiene `ticket_id IS NULL`.
- El inventario disponible nunca resulta negativo (`current_stock - reservas activas >= 0`).
- Cada venta confirmada tiene una cotización y un pago completado con actor/fecha; un quote no produce más de una venta.
- Comparar IDs y conteos de registros preexistentes fuera del fixture cuya eliminación fue aprobada; el informe de migración separa cada fila nueva, actualizada y removida.

## Limpieza de filas de prueba

Probar la operación de cleanup únicamente en una copia descartable de la base autorizada. Primero validar que el manifiesto contiene exactamente los ocho IDs revisados y que las dependencias/FKs coinciden con el preflight guardado. Una discrepancia debe terminar con cero filas borradas. La validación satisfactoria debe enumerar conteos anteriores/posteriores por tabla y confirmar que ningún ticket `SALE` ajeno al fixture se modificó.
