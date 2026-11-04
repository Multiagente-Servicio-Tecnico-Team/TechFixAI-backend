# Research: Gestión de clientes comerciales

**Fecha**: 2026-11-03  
**Fuente de verdad**: especificación 007, código backend y esquema PostgreSQL vigente consultado previamente en modo solo lectura. El archivo `contexto/tablas postgres v2.sql` no se trata como historial de migraciones.

## Decisiones

### 1. Conservar la identidad de acceso y resolver el perfil comercial en el límite de aplicación

- **Decisión**: mantener `users` y la sesión firmada sin cambios de autenticación; agregar `customers` con `user_id` opcional, único y verificable. Los casos de uso reciben el ID de sesión y resuelven el `customer_id` internamente.
- **Racional**: `SessionCustomer.id` en `app/accounts/session.py` representa hoy `users.id`. `app/adapters/api/chat.py` llama `ListCustomerTickets`, y `app/database/repository.py` filtra `tickets.customer_id` como ID de usuario. Esto evita propagar la interpretación antigua de ID a las nuevas relaciones comerciales.
- **Alternativas**: reutilizar `users` para personas manuales (rechazada: requiere cuentas ficticias y credenciales); cambiar auth para usar customer ID (rechazada: innecesario y rompería sesiones/roles existentes).

### 2. Migración expand/backfill/validate/contract y registro explícito de versión

- **Decisión**: migración estructural aditiva: crear perfil/relaciones nuevas como nullable, backfill conservador, verificar conteos/huérfanos/propiedad, actualizar escritores/lectores y solo después aplicar NOT NULL/checks y retirar dependencias antiguas en una etapa posterior. Antes, reconciliar migraciones 003–005 contra el esquema vivo; agregar ledger de migraciones sin marcar como aplicados scripts solo porque existen.
- **Racional**: `sql/migrations/003_accounting_entries.sql`, `004_admin_ticket_management.sql`, `005_supplier_purchases.sql` son archivos de operaciones separadas y la BD observada no tenía tabla de ledger. No se puede probar el orden/aplicación solo desde Git.
- **Alternativas**: recrear el esquema desde el dump (rechazada: es destructivo y no conserva datos); migración big-bang con eliminación inmediata de FK/columnas (rechazada: difícil de recuperar y deja consumidores legacy rotos).

### 3. Vender sin ticket y mantener tickets para servicio

- **Decisión**: tickets representan servicio/seguimiento de taller. `DIRECT_SALE` quote lleva `customer_id` y `ticket_id NULL`; servicio/PC_BUILD conserva vínculo con ticket cuando represente trabajo de taller. Una venta/pedido se crea una sola vez cuando un ADMIN confirma un pago verificable.
- **Racional**: `app/database/repository.py` en `accept_ticket_quote` (cerca de 910) y `create_accepted_ticket_quote` (cerca de 1051) crean pagos y quotes con ticket; el segundo también traduce venta directa a ticket SALE. `app/application/quotes.py` requiere ticket para `accept_quoted_draft`.
- **Alternativas**: mantener ticket SALE (rechazada: contamina banco de reparaciones y exige ticket para venta directa); considerar ACCEPTED como pago (rechazada: la oferta no es evidencia de cobro).

### 4. Reservar con filas auditables y consumir mediante movimiento de inventario

- **Decisión**: al aceptar la cotización, bloquear los artículos en orden estable, comprobar `current_stock - reservas activas`, crear toda la reserva o ninguna y cambiar la oferta a ACCEPTED en una transacción. La reserva lleva vencimiento; rechazo/cancelación/vencimiento libera idempotentemente. El pago confirmado consume la reserva, descuenta stock y crea movimiento SALE asociado a una línea de venta.
- **Racional**: `sql/migrations/005_supplier_purchases.sql` y `app/adapters/persistence/purchases.py` ya usan transacción, `FOR UPDATE`, actor, stock_before/after y `inventory_movements` para recepciones. No hay reserva ni movimiento de salida actual. `app/adapters/persistence/inventory.py` permite alterar `current_stock`, por lo que el administrador de inventario también debe bloquear la fila y prevenir que stock quede por debajo de reservas activas.
- **Alternativas**: descontar stock en aceptación (rechazada: producto no pagado aparenta vendido); usar solo un contador mutable sin registros por línea (rechazada: peor trazabilidad/liberación); usar `FOR SHARE` de lectura de catálogo (rechazada: no serializa confirmación de oferta).
- **Ledger de movimientos**: ampliar `inventory_movements` aditivamente con `sales_order_item_id` nullable y permitir `purchase_receipt_item_id` nullable, manteniendo una constraint XOR para exigir exactamente un origen. Conservar unicidad por origen y permitir `PURCHASE_RECEIPT` o `SALE`; cada movimiento conserva before/after, cantidad, actor y snapshot.

### 5. Segmentar efectos asociados a ticket según el agregado comercial

- **Decisión**: los pagos, reembolsos y consultas de cliente siguen `customer_id`+quote/payment; `ticket_id` queda nullable/derivable para servicio. Logística de taller conserva ticket; logística de venta apunta a sales order. Garantía de equipo atendido conserva ticket; garantía de producto vendido apunta a pedido/venta. Mantener auditoría con actor `users.id` en cada agregado nuevo.
- **Racional**: `request_refund` (~1968) copia `payments.ticket_id`; `create_logistics_record` (~1264) consulta propiedad por ticket; `create_warranty_claim` (~1216) requiere ticket, y `create_order_warranty` (~1355) busca quote vía ticket. Las rutas de negocio existentes no soportan una venta sin ticket.
- **Alternativas**: dejar las FK como están y usar tickets fantasma (rechazada: mantiene acoplamiento y confunde el caso de servicio); eliminar todos los flujos dependientes del ticket (rechazada: rompe reparación/garantía logística vigentes).

### 6. Limpieza de fixture independiente de la migración estructural

- **Decisión**: operación separada para borrar únicamente los ocho tickets SALE que el propietario confirmó como prueba y las filas dependientes verificadas para ese conjunto. Obtener IDs exactos de la base de prueba autorizada en implementación; validar cantidad, snapshot de dependencias, estados y entorno, producir backup y conteos; abortar en discrepancia; borrar en una transacción con orden FK. No seleccionar pagos por estatus ni usar `WHERE request_type='SALE'` genérico.
- **Racional**: la base consultada tenía 8 tickets SALE, 2 de ellos con quotes, 4 con payments; todos los 6 pagos existentes eran PENDING. La consulta de tickets dependientes no equivale a conocer todos los hijos de cada ticket. `ticket_audit_events.ticket_id` usa `ON DELETE RESTRICT` en migración 004. La selección debe partir del set exacto de ticket y recorrer FKs reales del destino.
- **Alternativas**: borrar cualquier ticket SALE del destino (rechazada: podría borrar datos reales); ejecutar limpieza como parte inseparable de migración DDL (rechazada: aumenta impacto y dificulta auditar/repetir por separado).

## Evidencia de arquitectura y pruebas afectadas

- Sesión y listado cliente: `app/accounts/session.py`, `app/adapters/api/chat.py`, `app/application/tickets.py`, `app/adapters/persistence/tickets.py`.
- Alta/consulta de tickets y presupuestos: `app/adapters/api/admin_tickets.py`, `app/adapters/persistence/admin_tickets.py`, `app/database/repository.py`.
- Inventario y compras/recepciones: `app/adapters/persistence/inventory.py`, `app/adapters/persistence/purchases.py`, `sql/migrations/005_supplier_purchases.sql`.
- Dependencias: `app/application/refunds.py`, `warranties.py`, `logistics.py`; repositorio alrededor de 1199–1355 y 1968.
- Pruebas a reconciliar: `tests/contract/patterns/test_service_flow_contract.py`, `test_quote_contract.py`, `tests/integration/test_refund_requests_integration.py`, `test_hierarchical_refund_flow.py`, `test_hierarchical_workflows.py`, `test_decentralized_refund_flow.py`, `test_pattern_api.py`, además de contratos y pruebas admin ticket/inventory.
- Tres patrones: `app/adapters/patterns/{hierarchical,decentralized,orchestrator}.py` y sus agentes. La capa de política persistente debe compartirse; no asumir que hoy los tres soportan herramientas equivalentes.
