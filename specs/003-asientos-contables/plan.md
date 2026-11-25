# Implementation Plan: Registro y trazabilidad de asientos contables

**Branch**: `003-asientos-contables` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-asientos-contables/spec.md`

## Summary

Agregar una capacidad contable manual y exclusiva del personal `ADMIN` en la API backend existente. Cada solicitud crea directamente un asiento confirmado, compuesto por líneas de debe/haber balanceadas y asociado al `ADMIN` autenticado. Las escrituras, sus líneas y su auditoría se guardan en una transacción; las correcciones se expresan como reversiones vinculadas. Se añade una migración PostgreSQL aditiva, rutas administrativas para categorías/listado/alta/detalle/reversión y un contrato OpenAPI para que el repositorio frontend pueda definir después su propia vista.

El alcance no contabiliza automáticamente cotizaciones, pagos, reembolsos ni compras, no modifica datos de clientes y no genera/presenta libros electrónicos PLE.

## Technical Context

**Language/Version**: Python 3.12 (versión documentada por el backend)  
**Primary Dependencies**: FastAPI 0.142.2, Pydantic 2, SQLAlchemy 2.1.1, pg8000 1.31.5, PostgreSQL; sin dependencia nueva de terceros  
**Storage**: PostgreSQL; el esquema actual ampliado no contiene entidades de asientos  
**Testing**: pytest con pruebas unitarias, de contrato e integración aislada; PostgreSQL de prueba para comprobar migración, concurrencia y restricciones diferidas  
**Target Platform**: Servicio HTTP del backend TechFix.AI (desarrollo local y despliegues existentes)  
**Project Type**: API web backend en capas domain/application/adapters/infrastructure  
**Performance Goals**: Objetivo inicial de p95 ≤ 1 s para listado de 50 elementos y detalle/alta en entorno de prueba con 10.000 asientos; medir en PostgreSQL de prueba, sin declarar SLA de producción  
**Constraints**: Crear y revertir solo con sesión `ADMIN`; todas las importaciones y verificaciones financieras deben completarse antes de confirmar la transacción; monto `Decimal` PEN de dos decimales; no editar/eliminar asientos confirmados; migración versionada aditiva, nunca ejecutar los scripts de recreación sobre datos existentes  
**Scale/Scope**: Un libro interno para la operación del taller; paginación inicial 50 por página y máximo 100; sin carga masiva, múltiples libros/empresas, monedas distintas, catálogo oficial PCGE, exportación PLE ni integración automática con transacciones comerciales

## Constitution Check

### Gate previo a investigación

- **Reglas de negocio y exactitud financiera**: PASS. El dominio calcula con `Decimal`, valida lados positivos y balance exacto; los valores monetarios de API se serializan como cadenas.
- **Persistencia autorizada**: PASS. La identidad viene de la cookie verificada; solo `ADMIN` puede escribir o consultar. Ningún agente/LLM crea asientos.
- **Separación de capas**: PASS. Reglas en `app/domain`, casos de uso/puertos en `app/application`, FastAPI y repositorio en `app/adapters`, composición en `app/infrastructure`.
- **Cambio de esquema trazable**: PASS. Nueva migración versionada, aditiva y ejecutable únicamente contra una BD de prueba autorizada antes de cualquier despliegue.
- **Privacidad/trazabilidad**: PASS. Guardar actor, acción, fecha y relación de reversión; no guardar sesión, credenciales o texto de excepciones.
- **Pruebas y comparabilidad**: PASS. Pruebas unitarias, contrato de API e integración para roles, balance, idempotencia, reversión, rollback y concurrencia.

### Gate posterior al diseño

- **Diseño consistente con la constitución**: PASS, sujeto a verificar que la implementación mantiene transacción única y no conecta el asiento a pagos `PENDING` ni a los flujos multiagente.
- **Sin excepción constitucional**: PASS. No se cambia el esquema de roles, no se incorpora tecnología nueva ni se altera el contrato de chat.

## Research Summary

Las decisiones de dominio, transacciones, numeración, seguridad, categorías y alcance tributario se documentan en [research.md](research.md). El diseño de entidades está en [data-model.md](data-model.md); las rutas y estructuras HTTP en [contracts/accounting.openapi.yaml](contracts/accounting.openapi.yaml).

## Project Structure

### Documentation (this feature)

```text
specs/003-asientos-contables/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── accounting.openapi.yaml
├── checklists/
│   └── requirements.md
└── tasks.md                         # generado por $speckit-tasks
```

### Source Code (repository root)

```text
app/
├── domain/accounting.py             # entidad, montos y reglas de balance
├── application/
│   ├── accounting.py                # crear/listar/consultar/revertir
│   ├── errors.py                    # errores tipados si se amplía el catálogo
│   └── ports.py                     # puerto del repositorio contable
├── adapters/
│   ├── api/accounting.py            # rutas y DTO HTTP
│   └── persistence/accounting.py    # adaptador del repositorio PostgreSQL
├── accounts/session.py              # guard ADMIN reutilizable
└── infrastructure/chat_app.py      # composición del router y adaptador
sql/migrations/
└── 003_accounting_entries.sql      # esquema, índices, categorías y restricciones
tests/
├── unit/domain/test_accounting.py
├── unit/application/test_accounting.py
├── unit/adapters/test_accounting_repository.py
├── integration/test_accounting_api.py
├── integration/test_accounting_postgres.py
└── contract/test_accounting_contract.py
```

**Structure Decision**: Extender el backend existente en vez de crear un servicio paralelo. La API contable se registra al componer el mismo FastAPI que chat y cuentas, pero en un router independiente. El repositorio contable será una responsabilidad nueva dentro del adaptador de persistencia y no se acoplará a `ServiceRepository` del chat/tickets.

## Complexity Tracking

No hay excepciones a la constitución ni nuevos proyectos o dependencias. La restricción agregada de balance de líneas es necesaria para sostener la integridad contable y se verifica en dominio y PostgreSQL.
