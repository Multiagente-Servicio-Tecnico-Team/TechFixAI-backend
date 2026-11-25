# Contrato de capacidades y políticas compartidas

Cada capacidad administrativa tiene un identificador allowlisted, conjunto de roles, tipo de operación, esquema validado y adaptadores `read`, `prepare` y `execute` donde corresponda. El chat ADMIN usa salida estructurada para seleccionar una capacidad; no registra herramientas SQL genéricas. Las escrituras separan `prepare` (sin efecto) y `execute` (solo tras confirmación válida).

## Invariantes

1. El rol y actor vienen exclusivamente de la sesión verificada.
2. La lista de acciones permitidas se limita al catálogo ADMIN antes de invocar el modelo. CUSTOMER/TECHNICIAN no pueden acceder a la ruta, el servicio ni a una capacidad ADMIN.
3. Los argumentos sugeridos por el LLM se validan como entrada no confiable; no pueden contener `user_id`, `customer_id` de autoridad, SQL, ruta, URL o rol.
4. Las lecturas comerciales verifican alcance. Los datos transaccionales se leen de PostgreSQL.
5. `prepare` no persiste cambios de negocio. Devuelve vista previa y payload normalizado asociado a la propuesta efímera del actor/conversación.
6. `execute` revalida permisos, estado, stock/precio/importe/referencias y usa clave idempotente.
7. Errores distinguen `forbidden`, `not_found`, `conflict`, `invalid`, `unavailable`; jamás devuelven excepción del proveedor ni contenido sensible.
8. Cancelar una propuesta no invoca el ejecutor. Confirmación ambigua no se interpreta como aprobación.

## Capacidades con actor auditado

- Tickets, clientes, inventario/movimientos, compras y recepciones, órdenes/recepciones, cotizaciones/pagos y asientos usan el ADMIN autenticado en sus operaciones existentes.
- Alta y actualización de proveedores escriben el actor y los cambios en `supplier_audit_events`; habilitar estas escrituras requiere aplicar la migración 016.
- El servicio ADMIN mantiene el identificador de patrón para aislar la conversación y comparar trazas. Sus capacidades no dependen de la topología CUSTOMER.

