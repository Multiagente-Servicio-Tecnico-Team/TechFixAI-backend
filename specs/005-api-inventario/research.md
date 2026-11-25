# Research: API de inventario

**Feature**: [spec.md](spec.md)  
**Date**: 2026-11-02

## Hallazgos del sistema actual

- TechFixAI-frontend/src/features/workshop/inventoryApi.js ya espera GET/POST /api/inventory/parts y PUT/DELETE /api/inventory/parts/{code}. Espera {parts: [...]}, {part: ...} y 204 al borrar; envía cookie con credentials: include.
- El adaptador convierte code, description, unit_price, current_stock y minimum_threshold a sku, compat, price en céntimos, stock y min. Envía el precio como texto decimal.
- Inventory.jsx hace búsqueda, filtros de categoría/stock, orden, métricas y páginas de cuatro elementos en cliente; no requiere filtros server-side.
- src/domain/inventory.js fija cinco categorías, pero el esquema y la semilla incluyen categorías adicionales. La API debe conservarlas y ofrecer una consulta de categorías; el consumo dinámico necesitará ajuste frontend posterior.
- app/infrastructure/chat_app.py compone la API y registra rutas de chat, tickets y contabilidad. CORS permite GET/POST/PATCH/DELETE, pero no PUT; sin corregirlo el browser bloquea actualizaciones.
- SessionGuard ofrece require_user, require_customer y require_admin. Los roles existentes incluyen ADMIN, TECHNICIAN y CUSTOMER. El guard de inventario debe aceptar los dos primeros sin cambiar las rutas administrativas actuales.
- contexto/tablas postgres v2.sql define spare_parts con código único, NUMERIC(10,2), stock y mínimo no negativos, active y timestamps. quote_details.spare_part_id tiene ON DELETE RESTRICT; purchase_order_items.spare_part_id usa ON DELETE SET NULL.
- app/database/repository.py ya consulta catálogo para agentes; AccountingRepositoryAdapter ilustra SQL parametrizado y sesiones. Las rutas administrativas de tickets ejemplifican Pydantic y autorización.

## Decisiones

### Contrato compatible con frontend

**Decision**: Preservar paths, métodos, payloads y respuesta que espera inventoryApi.js; añadir GET /api/inventory/categories.

**Rationale**: El cliente ya existe. La ruta de categorías cubre taxonomía adicional sin romper la pantalla actual.

**Alternatives considered**: Cambiar rutas y migrar el frontend primero, o enviar categorías solo como datos repetidos en repuestos. Se conserva el contrato actual y se añade una operación explícita.

### Autorización de personal

**Decision**: ADMIN y TECHNICIAN pueden usar inventario; CUSTOMER recibe 403 y sesión inválida 401.

**Rationale**: Coincide con “personal del taller” de la pantalla y los roles existentes.

**Alternatives considered**: Solo ADMIN impediría al técnico usar su ruta; cualquier usuario autenticado expondría/modificaría el catálogo.

### Eliminación física protegida por FK

**Decision**: Borrar físicamente si no existen referencias a presupuestos; devolver 409 y conservarlo si quote_details lo referencia.

**Rationale**: El frontend espera 204 o 409 “en uso”; la FK preserva la historia de cotización.

**Alternatives considered**: Soft delete universal. Aunque existe active, se mantiene el comportamiento esperado por el contrato del cliente y no se altera el esquema.

### Dinero exacto

**Decision**: Recibir y devolver precio como string decimal con dos posiciones, validar con Decimal y persistir en NUMERIC(10,2).

**Rationale**: El frontend convierte a céntimos y serializa texto; se evita aritmética binaria y redondeo silencioso.

### CORS para PUT

**Decision**: Autorizar PUT para los orígenes ya configurados.

**Rationale**: El formulario usa PUT; el preflight de navegador falla si CORS no incluye el método.

**Alternatives considered**: Cambiar frontend a PATCH. Se descarta porque el cliente actual hace reemplazo completo con PUT.

### Sin migración

**Decision**: Reutilizar spare_parts y sus FK. No agregar tablas de categoría ni bitácora de movimientos.

**Rationale**: Los campos requeridos ya están persistidos; el formulario ajusta stock absoluto y el alcance es conectar el CRUD.

## Cuestiones resueltas

- Las categorías son cadenas libres de máximo 50 caracteres; no hay tabla ni enum.
- La lista completa se usa para que frontend aplique sus filtros y paginación actuales.
- No quedan decisiones bloqueantes ni NEEDS CLARIFICATION.
