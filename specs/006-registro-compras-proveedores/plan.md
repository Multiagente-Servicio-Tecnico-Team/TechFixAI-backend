# Implementation Plan: Registro de compras a proveedores

**Branch**: `006-registro-compras-proveedores` | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

## Summary

Implementar en el backend un registro administrativo de comprobantes recibidos, separado de las órdenes de compra actuales. La solución agrega entidades de compra, líneas, recepciones y auditoría; extiende proveedores con los datos comerciales que exige el spec; y registra movimientos de inventario solo al confirmar recepciones. Las reglas viven en dominio/aplicación y el adaptador PostgreSQL ejecuta cada recepción e incremento de stock en una transacción. El detalle de pagos se limita al método y estado pagado/pendiente; no crea asientos contables ni procesa pagos.

## Technical Context

**Language/Version**: Python 3.11 (versión del proyecto)  
**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy Core (`text()`), PostgreSQL  
**Storage**: PostgreSQL existente, migración SQL aditiva bajo `sql/migrations/`  
**Testing**: pytest; pruebas unitarias de dominio/aplicación, contrato API e integración de persistencia con PostgreSQL de prueba o fixtures aislados siguiendo patrones existentes  
**Target Platform**: Servicio backend TechFix.AI  
**Project Type**: API backend por capas  
**Performance Goals**: Listas paginadas; recepción atómica con una transacción por solicitud; evitar consultas por línea mediante lecturas/escrituras agrupadas  
**Constraints**: ADMIN exclusivamente; PEN en versión inicial; importes `Decimal`/`NUMERIC(14,2)`; conservar snapshots históricos aunque proveedor o repuesto cambien; impedir doble aplicación de inventario; no emitir PLE ni asientos  
**Scale/Scope**: CRUD acotado de proveedores y compras, consulta paginada/detalle, cancelación y recepción completa o parcial en eventos repetibles hasta completar cantidades facturadas

## Constitution Check

| Principio / restricción | Evaluación | Evidencia o tratamiento |
|---|---|---|
| Reglas de negocio compartidas | PASS | La lógica de compras no pertenece a patrones LLM; dominio/aplicación valida las mismas reglas para toda llamada API. |
| Persistencia autorizada y verificable | PASS | Sólo sesión ADMIN; recepción es una confirmación explícita; identidad nunca viene del cuerpo. |
| Datos financieros exactos | PASS | `Decimal` en Python y `NUMERIC(14,2)` en PostgreSQL; compras no disparan asientos. |
| Evidencia antes que invención | PASS | Sólo se vinculan productos del catálogo; líneas conservan nombre/código y costo como snapshot. |
| Seguridad y privacidad | PASS | Rutas con `require_admin`, no-store, errores sin datos sensibles, consultas paginadas. |
| Cambios de esquema trazables | PASS | Migración aditiva y transaccional, sin `DROP`; migración sólo se aplica tras respaldo/verificación de destino. |
| Pruebas comparables | PASS | Contrato API y pruebas comunes de dominio/persistencia cubren autorización, totales, duplicados y stock idempotente. |

**Gate inicial**: PASS. No se detectan excepciones a la constitución.

## Phase 0: Research

Ver [research.md](research.md). Confirma separación de compra y orden, estrategia de recepción repetible/idempotente, transacción de stock, snapshots y ausencia de pagos parciales/PLE/asientos.

## Phase 1: Design & Contracts

- Modelo y estados: [data-model.md](data-model.md).
- Contratos HTTP: [contracts/purchases.openapi.yaml](contracts/purchases.openapi.yaml).
- Guía ejecutable de validación manual: [quickstart.md](quickstart.md).

### Constitución después del diseño

**Gate post-diseño**: PASS. Las escrituras usan ADMIN autenticado; recepción, movimiento y auditoría se confirman en una transacción; las claves únicas/idempotentes resguardan reintentos; las líneas conservan snapshots; los pagos no se contabilizan automáticamente. Sin violaciones que requieran Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/006-registro-compras-proveedores/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── purchases.openapi.yaml
```

### Source Code (repository root)

```text
app/
├── domain/
│   └── purchases.py                 # Tipos, estados y reglas invariantes
├── application/
│   ├── purchases.py                 # Casos de uso y validación
│   └── ports.py                     # Puerto de persistencia si aplica al patrón actual
├── adapters/
│   ├── api/purchases.py             # Rutas ADMIN y modelos HTTP
│   └── persistence/purchases.py     # Repositorio PostgreSQL y transacciones
└── infrastructure/chat_app.py       # Composición e inclusión de router
sql/migrations/
└── 005_supplier_purchases.sql       # Extensiones aditivas del esquema
tests/
├── unit/domain/                     # Totales, transiciones, recepción
├── unit/application/                # Casos de uso/puertos
├── contract/                        # Forma y permisos del API
└── integration/                     # Unicidad, transacción y stock
```

**Structure Decision**: Se mantiene la arquitectura existente `domain` / `application` / `adapters` / `infrastructure`; persistencia PostgreSQL usa SQLAlchemy Core como `app/adapters/persistence/inventory.py` y `accounting.py`. Se crea un router `/api/admin/purchases` independiente del CRUD de inventario y de `purchase_orders`.

## Complexity Tracking

Sin violaciones a la constitución. La entidad de recepción separada se justifica por la necesidad de conservar recepciones parciales/repetibles y que cada incremento de stock sea auditable e idempotente.
