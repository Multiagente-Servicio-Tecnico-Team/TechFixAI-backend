# Implementation Plan: Gestión de clientes comerciales

**Branch**: `007-gestion-clientes-comerciales` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-gestion-clientes-comerciales/spec.md`

## Summary

Separar `users` como identidad de acceso de `customers` como identidad comercial, migrar de forma compatible tickets/cotizaciones/pagos y eliminar del modelo los tickets de venta. El backend conservará tickets para servicio, permitirá cotizaciones directas de venta, y solo creará pedidos cuando un ADMIN confirme un pago verificable. La aceptación de una oferta de venta reservará inventario de forma transaccional hasta el pago o vencimiento. El cambio se desplegará en etapas con migración aditiva, compatibilidad temporal, contratos comunes y una limpieza de prueba separada y preflightada.

## Technical Context

**Language/Version**: Python 3.14.4 en el entorno observado; el repositorio no fija una versión mínima/máxima reproducible.

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy Core/ORM, PostgreSQL/psycopg, pytest; LangGraph para flujos de chat existentes.

**Storage**: PostgreSQL. La base vigente es fuente de verdad; el SQL de `contexto/tablas postgres v2.sql` es un script de reconstrucción y no determina el estado migrado.

**Testing**: pytest; pruebas unitarias, integración API/repositorio y contratos compartidos para los tres patrones.

**Target Platform**: Servicio backend Python consumido por el portal web y herramientas conversacionales; PostgreSQL en entorno local/de despliegue.

**Project Type**: Backend web API con capacidades de dominio y persistencia.

**Performance Goals**: Cero sobreventas incluso con aceptaciones simultáneas. Toda confirmación de pago, reserva/liberación y actualización de stock debe tener resultado atómico e idempotente. No hay SLO de latencia existente para estos endpoints.

**Constraints**: Mantener auth/cookie y roles existentes; derivar cliente de la sesión; `Decimal` para importes; no confiar en LLM para stock, pago ni escritura; preservar separación domain/application/adapters/infrastructure; compatibilidad de API durante transición; no realizar limpieza de datos hasta validar base destino, IDs y dependencias exactas.

**Scale/Scope**: Un nuevo modelo `customers`; tickets, cotizaciones, pagos, pedidos, reserva y movimientos de inventario; tres patrones de conversación; impactos de reembolso, garantía, logística, auditoría, migraciones y contratos. Base observada: 26 tablas públicas; 12 tickets en la consulta del 2026-11-03.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio/gate | Resultado | Justificación |
|---|---|---|
| Reglas compartidas entre patrones | PASS | Los contratos de negocio y pruebas se compartirán entre Jerárquico, Orquestador y Descentralizado; su topología puede seguir diferenciándose. |
| Escrituras autorizadas y verificables | PASS | Las operaciones de mutación usarán sesión verificada, permisos ADMIN/propietario y validación transaccional; el LLM no confirma pagos ni existencias. |
| Importes financieros exactos | PASS | Importes y cálculos usan Decimal/NUMERIC; pago y cotización mantienen estados distintos. |
| Seguridad/privacidad | PASS | El customer_id de cliente portal se resolverá desde cookie/sesión, nunca desde un ID libre del body; no se agregarán datos sensibles a trazas. |
| Esquema/migraciones trazables | PASS CON SALVEDAD | Se requiere reconciliar las migraciones manuales existentes, introducir ledger si no existe y hacer migración aditiva. La limpieza de filas de prueba tendrá paso separado y guardado, no se ejecutará sobre otras bases. |
| Cambios de migración seguros | PASS CON SALVEDAD | Hay ocho tickets SALE de prueba cuya eliminación fue aprobada. La excepción queda limitada al set exacto verificado en el destino autorizado; el resto de filas históricas se conserva. |
| Pruebas comparables | PASS | Contratos de propiedad, oferta/pago y reservas deben ejecutarse para entradas equivalentes en los tres patrones. |
| Separación arquitectónica | PASS | Lógica de negocio en dominio/aplicación; detalles SQL en adapters/persistencia; endpoints en adapters/API. Evitar ampliar más el repositorio monolítico. |

No se identifican violaciones constitucionales que requieran una excepción adicional. La eliminación de los datos de prueba está autorizada por el propietario y queda delimitada por FR-025; no se permite un borrado masivo por tipo.

## Project Structure

### Documentation (this feature)

```text
specs/007-gestion-clientes-comerciales/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/customer-commerce.openapi.yaml
└── tasks.md                 # siguiente fase ($speckit-tasks)
```

### Source Code (repository root)

```text
app/
├── accounts/                # sesión/auth existente; resolver customer en límite del caso de uso
├── domain/                  # entidades/errores y políticas de customer-commerce
├── application/              # casos de uso customers, quotes, payment, sales, reservations
├── adapters/
│   ├── api/                  # routers FastAPI admin y customer
│   └── persistence/          # repositorios PostgreSQL por capacidad
├── database/repository.py    # compatibilidad existente a reducir por etapas
└── agents/                   # integración de capacidades comerciales en los patrones
sql/migrations/               # migración estructural aditiva versionada
sql/operations/               # limpieza de datos de prueba separada y guardada
tests/
├── unit/
├── integration/
└── contract/patterns/        # mismas reglas de negocio para los tres patrones
```

**Structure Decision**: Backend existente en la raíz; conservar módulos y capas actuales. La nueva capacidad se incorpora en domain/application/adapters y una migración versionada. La limpieza aprobada no se mezcla con la migración estructural: se documenta como operación separada en `sql/operations/` para preflight, aprobación de destino y reporte.

## Implementation Sequence

1. **Reconciliar el estado de base y contratos**: verificar migraciones realmente aplicadas en el destino; la carpeta SQL no demuestra aplicación y la BD revisada carecía de ledger. Capturar respaldo y una línea base de conteos/relaciones. Incorporar ledger/reconciliación antes de registrar una migración nueva.
2. **Modelo de cliente e identidad**: migración aditiva `customers` y referencias nuevas opcionales; backfill uno-a-uno desde users y desde snapshots de ticket sin cliente; resolver sesión→customer en la capa de aplicación. No fusionar por teléfono/correo. Mantener columnas/vínculos viejos mientras consumidores existentes migran.
3. **Tickets de servicio**: exigir customer para altas nuevas, conservar snapshots de contacto, actor ADMIN independiente y cero o más cotizaciones de servicio; rutas portal/admin filtran por perfil comercial.
4. **Cotizaciones de venta directas**: permitir `quotes.ticket_id = NULL` para DIRECT_SALE, validar líneas y precio vigente, conservar snapshots; adaptar respuesta de chat para devolver quote_id y rutas de consulta/aceptación. Retirar la creación implícita de tickets SALE de los flujos habilitados.
5. **Reserva y movimientos de stock**: añadir reservas de encabezado/línea auditables e índices únicos/idempotentes. Aceptar quote en transacción: bloqueo consistente de artículos, cálculo `current_stock - reservas activas`, reserva completa o ninguna, estado ACCEPTED y payment PENDING. Vencimiento/cancelación/rechazo libera reserva. Confirmar pago consume reserva, reduce stock y añade salida `SALE`. Extender `inventory_movements` con `sales_order_item_id`, volver nullable `purchase_receipt_item_id` y exigir exactamente un origen por XOR; conservar datos/constraints de recepción existentes y los campos stock_before/after/actor/snapshots.
6. **Pagos, pedido, reembolso, logística y garantía**: pagos y reembolsos deben poder referenciar quote/customer/order sin ticket; los flujos de reparación pueden conservar ticket. Crear pedido una sola vez por quote/pago confirmado. Venta logística y garantía apuntan a pedido/venta; flujos de taller conservan ticket. Auditar autor, timestamp, origen y cambios sin guardar credenciales/texto sensible.
7. **Adaptar patrones y consumidores**: compartir políticas/casos de uso; integrar en patrones Jerárquico, Orquestador y Descentralizado según capacidades actuales, manteniendo el descentralizado experimental si su persistencia está simulada. No afirmar equivalencia donde no exista soporte.
8. **Limpieza de tickets SALE de prueba**: preflight separado, solo en la BD de prueba autorizada, identificar y congelar manifiesto exacto de los ocho IDs; contar hijos por FK, validar estados/IDs esperados y crear respaldo. Si hay discrepancia, abortar sin cambios. Borrar en orden FK dentro de transacción, incluyendo dependientes verificados pertenecientes al fixture; registrar counts por tabla y conservar reporte. No filtrar genéricamente todos los tickets SALE ni asumir que los seis pagos pendientes dependen del set.
9. **Cierre compatible y retiro de legacy**: después de consumidores y datos validados, exigir nuevas relaciones, crear índices/constraints, pasar lecturas/escrituras al modelo nuevo y retirar referencias antiguas en una etapa posterior documentada y reversible hasta donde los datos permitan.

## Risks and Mitigations

- **Migraciones aplicadas fuera del ledger**: reconciliar con catálogo real de PostgreSQL, fingerprints y conteos antes de escribir; nunca marcar todo como aplicado por existencia del archivo.
- **Venta online ligada hoy a ticket**: hacer explícito el `quote_id` persistido en chat y mantener lectura de historial; contrato coordinado con frontend en feature separado.
- **Sobreventa por aceptación concurrente o edición administrativa de stock**: bloquear filas de inventario en orden estable; ninguna modificación manual puede dejar stock físico por debajo de reservas activas.
- **FK de venta amarradas al ticket**: inventariar relaciones del esquema vivo en planning/implementación; cambiar garantía/logística/reembolso en su propio límite de dominio, no eliminar restricciones a ciegas.
- **Repetición de pago o expiración**: idempotency keys y restricciones únicas; liberar reservas idempotentemente; verificar expiraciones aun si scheduler no está disponible al consultar/aceptar.
- **Eliminación de datos de prueba**: paso separado, manifiesto exacto, conteo pre/post, respaldo, transacción y aborto seguro en discrepancia.

## Post-Design Constitution Check

Los artefactos de diseño mantienen los gates iniciales. Las nuevas operaciones financieras e inventario quedan en capacidades compartidas con pruebas de contrato entre patrones; los repositorios aplican transacciones e identidad resuelta desde sesión. La limpieza sigue aislada, con límites por manifiesto/destino y respaldo. No se detectan violaciones nuevas ni quedan decisiones críticas sin resolver.

## Complexity Tracking

No se solicita introducir un cuarto proyecto ni una nueva infraestructura. Se amplía el backend existente y se limita la complejidad a cambios requeridos por el modelo comercial, la reserva y la eliminación del acoplamiento a ticket.
