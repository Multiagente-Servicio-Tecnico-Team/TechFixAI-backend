# Implementation Plan: Trazabilidad de movimientos de inventario

**Branch**: `[008-trazabilidad-movimientos-inventario]` | **Date**: 2026-11-08 | **Spec**: [spec.md](spec.md)

**Input**: `specs/008-trazabilidad-movimientos-inventario/spec.md`

## Summary

Cada variación debe actualizar saldo y movimiento auditable dentro de una sola operación. El CRUD deja de escribir stock; se agregan apertura, ajuste por conteo e historial. Compras recibidas y ventas confirmadas conservan sus movimientos mediante una regla transaccional común. La migración toma un punto de corte del saldo actual sin atribuirlo a usuarios falsos ni inventar eventos previos.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL  
**Storage**: `spare_parts`, `inventory_movements`, `inventory_reservations`, `inventory_reservation_items`, `purchase_receipt_items`, `sales_order_items`, `users`  
**Testing**: pytest; pruebas unitarias, contractuales y de integración PostgreSQL  
**Target Platform**: API HTTP backend TechFix.AI  
**Project Type**: Servicio web por capas domain/application/adapters/infrastructure  
**Performance Goals**: Historial filtrado y paginado; no se fija latencia nueva sin medición base. Índice para artículo y fecha/ID.  
**Constraints**: Sesión actual; ADMIN/TECHNICIAN; stock no negativo ni menor que reservas; movimientos inmutables; migración aditiva; sin cambios de frontend o ejecución de migración en esta fase.  
**Scale/Scope**: Inventario de un taller; ajustes de un artículo y operaciones de compra/venta con varias líneas; consulta paginada por artículo.

## Constitution Check

| Principio | Estado | Evidencia |
|---|---|---|
| Reglas de negocio compartidas | PASS | Operación común aplica delta, saldo y movimiento desde ajuste, recepción y venta. |
| Persistencia autorizada | PASS | Actor humano de la cookie verificada; nunca viene del payload. Roles ADMIN/TECHNICIAN. |
| Separación por capas | PASS | Validación/delta en dominio-aplicación; SQL/transacciones en adaptador; HTTP en API. |
| Esquema trazable | PASS | Migración incremental y separada del script de reconstrucción; bootstrap vacío se actualiza. |
| Auditoría/seguridad | PASS | Actor, motivo, clave idempotente, inmutabilidad y errores sin SQL/secretos. |
| Pruebas | PASS | Contrato e integración verifican apertura, ajustes, compras, ventas, permisos, carrera y rollback. Paridad de grafos no aplica. |
| Dependencias | PASS | Se reutilizan dependencias existentes, sin servicios nuevos. |

Sin excepciones constitucionales.

## Estructura de proyecto seleccionada

```text
app/domain/inventory.py
app/application/inventory.py
app/application/ports.py
app/application/errors.py
app/adapters/api/inventory.py
app/adapters/persistence/inventory.py
app/adapters/persistence/inventory_movements.py   # operación compartida propuesta
app/adapters/persistence/purchases.py              # reutiliza operación compartida
app/adapters/persistence/sales_quotes.py            # reutiliza operación compartida
app/infrastructure/chat_app.py                     # router existente/montaje
sql/migrations/20261108_inventory_movement_traceability.sql
sql/esquema-vacio-produccion.sql                   # bootstrap para nuevas bases
specs/008-trazabilidad-movimientos-inventario/contracts/inventory-movements.openapi.yaml
tests/unit/test_inventory_movements.py
tests/contract/test_inventory_movements_contract.py
tests/integration/test_inventory_movements_api.py
tests/integration/test_inventory_movement_migration.py
```

**Structure Decision**: Extender módulos existentes. Una función de persistencia aplica el cambio dentro de la transacción que ya posee el caso de uso; las reglas puras permanecen en dominio. Repetir búsqueda transversal de escrituras de `current_stock` antes de cerrar.

## Phase 0: Research

Decisiones y evidencias en [research.md](research.md): arquitectura existente; tabla y constraints actuales; tres caminos de escritura; reservas; idempotencia; rol de personal; tratamiento del corte; checkout sin carpeta de migraciones.

La futura migración inicial se propone en `sql/migrations/` como script incremental, versionado por fecha y reejecutable. La BD de prueba conectada desde `.env` fue contrastada en solo lectura el 2026-11-08: las columnas y restricciones revisadas de las siete tablas de inventario coinciden con `sql/esquema-vacio-produccion.sql`. El estado observado fue 431 artículos/2,618 unidades, un movimiento histórico y cero reservas activas; el corte debe calcular datos al ejecutarse, nunca codificar esos conteos. Antes de aplicar en una BD destino se vuelve a comparar su esquema; el dump destructivo no es migración.

## Phase 1: Design & Contracts

- [data-model.md](data-model.md): entidades, campos, tipos, signos, orígenes, corte y retiro.
- [contracts/inventory-movements.openapi.yaml](contracts/inventory-movements.openapi.yaml): apertura, ajuste e historial con cookie, idempotencia y errores.
- [quickstart.md](quickstart.md): validación manual y automatizada prevista; no se ejecutaron pruebas en planificación.
- Migración aditiva para ampliar tipos/constraints, actor SYSTEM del corte, motivo/idempotencia, índices y aperturas de corte; actualizar `sql/esquema-vacio-produccion.sql` para bootstrap. No ejecutar scripts destructivos.

### Constitution re-check after design

PASS. Actor humano siempre autenticado; corte distinguido como SYSTEM; todas las rutas usan una transacción; datos anteriores preservados; capas conservadas; ninguna dependencia nueva.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Escritura de stock fuera de caminos conocidos | Búsqueda exhaustiva y helper común aplicado a CRUD, recepción y venta. |
| Ajuste deja reservas sin cubrir | Bloqueo del repuesto y rechazo atómico si conteo < reserva activa. |
| Carrera de saldo | Lock de fila; orden ascendente de locks en operaciones multilínea. |
| Retry duplica movimiento | Idempotency-Key + hash y replay; compra/venta mantienen unicidad por origen. |
| Corte coincide con mutación de stock | Serializar escrituras durante el corte; validación en PostgreSQL. |
| BD destino distinta al esquema de referencia | Inspeccionar antes de futura migración; no ejecutar contra `.env` por defecto. |

## Complejidad

No hay dependencias o servicios nuevos. Se amplía la entidad existente y se agrega una migración de corte necesaria para que los saldos futuros sean reconciliables sin falsificar la historia.

