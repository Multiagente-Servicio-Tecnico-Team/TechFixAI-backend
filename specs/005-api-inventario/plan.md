# Implementation Plan: API de inventario

**Branch**: [005-api-inventario] | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from specs/005-api-inventario/spec.md

## Summary

Publicar el CRUD de repuestos y la consulta de categorías que necesita el módulo de inventario del frontend. Se reutilizan las sesiones existentes, el esquema spare_parts, PostgreSQL y la arquitectura por capas. La respuesta coincide con inventoryApi.js; los precios se conservan como decimales exactos. La eliminación física solo se permite cuando no hay detalles de presupuesto dependientes. La interfaz usa PUT, por lo que se habilita ese método en CORS.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Pydantic 2, SQLAlchemy, PostgreSQL  
**Storage**: PostgreSQL existente; spare_parts, quote_details, purchase_order_items  
**Testing**: pytest, FastAPI TestClient; pruebas unitarias, de contrato e integración  
**Target Platform**: API HTTP backend TechFix.AI  
**Project Type**: Servicio web backend  
**Performance Goals**: Cargar el catálogo activo completo en una consulta; los filtros y la paginación visual siguen en el frontend. No se fija latencia nueva sin mediciones base.  
**Constraints**: Sesión por cookie; solo ADMIN/TECHNICIAN; dinero Decimal; sin migración; contrato compatible con el cliente; habilitar PUT en CORS.  
**Scale/Scope**: Catálogo de repuestos de taller; lista de activos, CRUD por código y categorías distintas.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio | Resultado | Evidencia |
|---|---|---|
| Reglas compartidas y separación por capas | PASS | Dominio/aplicación para reglas, adaptador de persistencia para SQL y adaptador API para HTTP. |
| Persistencia autorizada | PASS | Identidad desde cookie verificada; solo ADMIN y TECHNICIAN. |
| Datos financieros exactos | PASS | Decimal en backend y texto decimal de dos posiciones en el contrato. |
| Esquema ampliado y cambios trazables | PASS | Se reutiliza spare_parts; no se necesita migración. |
| Integridad del historial | PASS | quote_details permanece intacta; las referencias bloquean DELETE con 409. |
| Pruebas comparables | PASS | Unitarias, contrato y API para roles permitidos y denegados. La paridad entre grafos no aplica. |
| Dependencias | PASS | Se reutilizan FastAPI, Pydantic, SQLAlchemy, sesiones y PostgreSQL. |

No se identifican excepciones constitucionales ni ambigüedades que bloqueen el diseño.

## Project Structure

### Documentation (this feature)

    specs/005-api-inventario/
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    └── contracts/inventory.openapi.yaml

### Source Code (repository root)

    app/domain/inventory.py
    app/application/inventory.py
    app/application/errors.py                     # extender errores existentes si aplica
    app/adapters/persistence/inventory.py
    app/adapters/api/inventory.py
    app/accounts/session.py                       # autorización de personal
    app/infrastructure/chat_app.py                # registro del router y CORS
    tests/unit/test_inventory.py
    tests/contract/test_inventory_contract.py
    tests/integration/test_inventory_api.py

**Structure Decision**: Backend FastAPI existente con separación domain/application/adapters/infrastructure. Revisar y extender puertos/errores existentes antes de crear abstracciones. El adaptador encapsula SQL; las rutas no contienen consultas y dominio/aplicación no dependen de FastAPI ni SQLAlchemy.

## Phase 0: Research

Las decisiones y evidencias se encuentran en [research.md](research.md). Se revisaron cliente frontend, rutas, composición de API, sesión, adaptadores existentes y las claves foráneas del esquema ampliado.

## Phase 1: Design & Contracts

- [data-model.md](data-model.md) define el recurso y sus reglas.
- [contracts/inventory.openapi.yaml](contracts/inventory.openapi.yaml) fija rutas, payloads, autorización y errores.
- [quickstart.md](quickstart.md) describe validación reproducible.
- Sin migración SQL: las columnas y restricciones necesarias ya existen.

### Constitution re-check after design

PASS. The contract uses the verified session, preserves Decimal amounts and FK history, adds no schema or dependency, and keeps transport/database concerns outside domain rules. No exception requires complexity justification.

## Risks and Mitigations

| Riesgo | Mitigación |
|---|---|
| El frontend fija cinco categorías aunque la BD contiene más | El API no traduce ni limita categorías y expone el catálogo distinto; el consumo dinámico se hará en el frontend. |
| SessionGuard no tiene un guard específico de personal | Añadir chequeo explícito ADMIN/TECHNICIAN para inventario sin relajar guards administrativos. |
| CORS no permite PUT | Añadir PUT y comprobar preflight con credenciales. |
| DELETE viola FK histórica | Convertir el conflicto de integridad a 409 sin revelar SQL ni excepciones. |
| Decimal se serializa como float | Mantener string decimal y probar precisión. |

## Complexity Tracking

No hay violaciones que justificar.
