# Implementation Plan: Catálogo de cuentas y consultas contables

**Branch**: `009-catalogo-cuentas-consultas-contables` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-catalogo-cuentas-consultas-contables/spec.md`

## Summary

Añadir contabilidad por cuentas controladas, periodos mensuales y reportes de diario, mayor y balance de comprobación. La propuesta conserva el flujo actual de asientos confirmados, balanceados, inmutables y exclusivos de ADMIN; agrega una referencia versionada a cuentas sin cambiar los snapshots históricos; y calcula reportes desde asientos y reversiones confirmados. El catálogo inicial es el PCGE Modificado 2019 publicado por el MEF, como dato interno versionado y sin afirmar certificación SUNAT.

## Technical Context

**Language/Version**: Python 3.x con sintaxis de tipos moderna. El repositorio no fija formalmente una versión mínima; desplegar con el runtime compatible ya configurado y documentarlo antes de release.

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy, pg8000; `csv` de la biblioteca estándar para CSV y `openpyxl` para XLSX (dependencia nueva, generación en modo write-only para reducir memoria).

**Storage**: PostgreSQL existente. Las nuevas entidades se agregan a las tablas de asientos existentes mediante migración incremental; `sql/esquema-vacio-produccion.sql` es bootstrap y no sustituye migraciones.

**Testing**: pytest. Pruebas unitarias de reglas de catálogo y saldos; pruebas de contrato OpenAPI; pruebas de integración PostgreSQL para restricciones, migración, periodos, snapshots, reportes y reversión; validación de CSV/XLSX mediante lectura de los archivos generados.

**Target Platform**: Servicio backend Python en Linux con PostgreSQL, incluido el despliegue existente en Render.

**Project Type**: API backend modular con capas `domain`, `application`, `adapters` e `infrastructure`.

**Performance Goals**: Listas administrativas paginadas con tope actual de 100; informes paginados. Exportación inicial con máximo explícito de 10 000 filas, error visible si se excede y solicitud de reducir el rango/filtros; ajustar el límite con mediciones antes de release.

**Constraints**: Solo ADMIN; PEN; periodos por mes calendario; no contabilización automática de pagos/ventas/compras; no PLE; asientos confirmados inmutables; suma debe/haber exacta con Decimal. XLSX debe usar escritura en flujo para no retener el libro entero en memoria.

**Scale/Scope**: Una entidad/empresa y su catálogo interno; plan PCGE predeterminado más planes alternativos; lecturas de control de los asientos existentes y nuevos. No cubre contabilidad multientidad ni multimoneda.

## Constitution Check

- **Reglas de negocio compartidas — PASS**: Las validaciones contables residen en el dominio/aplicación y se aplican igual a todos los clientes de la API; no se delegan al frontend.
- **Persistencia autorizada — PASS**: Las escrituras exigen ADMIN autenticado, validación de cuenta imputable y periodo abierto; encabezado, líneas y auditoría se persisten atómicamente.
- **Datos financieros exactos — PASS**: Mantener Decimal y las restricciones actuales de debe/haber; reportes no recalculan ni inventan importes desde otras áreas.
- **Evidencia antes que invención — PASS**: Sembrar solo el PCGE Modificado 2019 del MEF con versión y fuente visibles; documentar que no valida régimen ni obligaciones fiscales.
- **Seguridad y privacidad — PASS**: Rutas administrativas ADMIN-only; eventos almacenan actor y cambios necesarios, sin trazas con contenido financiero innecesario ni secretos.
- **Cambios de esquema trazables — PASS CON PRECONDICIÓN**: El diseño usa migración aditiva versionada y preserva datos. Antes de crear/aplicar la nueva migración, reconciliar el ledger `schema_migrations` y la discrepancia de nomenclatura/checksum de la migración de inventario observada en el repositorio; no asumir que los dumps son migraciones.
- **Pruebas comparables — PASS / NO APLICA A PATRONES**: Esta capacidad administrativa no atraviesa los tres grafos multiagente. Se requieren pruebas comunes de contrato, roles, consistencia e integración.

**Gate**: Aprobado para diseño. La discrepancia de historial de migraciones es un bloqueo operativo de implementación hasta que se verifique el estado real de cada entorno; este plan no autoriza conectar o mutar la base.

## Design Decisions

1. **Catálogo versionado**: cargar `PCGE Modificado 2019` como plan Perú inicial, manteniendo código, denominación, jerarquía, naturaleza, saldo normal, vigencia y condición imputable; incluir fuente y edición. Un ADMIN puede crear planes alternativos. Solo un plan está marcado predeterminado para nuevas capturas; una solicitud de asiento identifica explícitamente el plan elegido.
2. **Snapshot contable**: añadir `accounting_plan_id` nullable en encabezado y `account_id` nullable en línea para compatibilidad histórica; conservar `account_code` y `account_name` existentes como snapshot obligatorio. Las nuevas interfaces deben enviar plan y account_id; como transici?n, si el plan se omite se usa el predeterminado y un `account_code` legado se resuelve por coincidencia exacta en ese cat?logo. `account_name` enviado por el cliente no se considera autoridad: el backend devuelve y persiste el nombre del cat?logo. Todas las l?neas deben resolverse a cuentas imputables del mismo plan. La reversión copia vínculo y snapshots.
3. **Historial sin inferencias**: dejar en NULL el vínculo de cuentas antiguas; reportarlas bajo el código/nombre snapshot con marca de cuenta histórica no vinculada. No mapear por igualdad textual ni migrar importes.
4. **Periodos y auditoría**: crear un registro único por año/mes, estado abierto/cerrado y transiciones inmutables de actor, fecha, estado anterior/nuevo y motivo de reapertura. Los meses se crean abiertos al habilitarse para el sistema; el cierre/reapertura es explícito de ADMIN. Cualquier nueva fecha de asiento/reversión debe resolver a un periodo abierto.
5. **Cálculo de reportes**: una consulta de dominio/aplicación compartida aplica los mismos filtros y reglas a JSON y exportaciones. Diario ordena por fecha/correlativo; mayor calcula saldo corrido según naturaleza de cuenta; balance agrupa saldo inicial, débitos, créditos y saldo final. Original y reverso se incluyen ambos una vez. Para código histórico sin naturaleza, presentar saldo firmado debe menos haber y marcar naturaleza desconocida, sin clasificarlo.
6. **Exportación**: CSV usa `csv` estándar, codificación UTF-8 con BOM para Excel en español; XLSX usa `openpyxl` en modo write-only. Ambos consumen el mismo conjunto ordenado y tienen filas/columnas/totales idénticos. Máximo inicial 10 000 filas por archivo con error claro, nunca truncamiento silencioso.
7. **Contratos y transición**: agregar contrato OpenAPI para planes/cuentas, periodos y reportes; actualizar el contrato contable existente para selección de plan/cuenta, errores de periodo cerrado y snapshots de respuesta. El repositorio frontend queda fuera de este plan; el backend mantiene una transici?n segura para el payload actual solo cuando cada c?digo de cuenta existe exactamente en el plan predeterminado. El frontend luego cambiar? a selecci?n de cuentas y plan expl?citos.
8. **Versionado de migraciones**: inspeccionar `schema_migrations` en el entorno objetivo y reparar primero la discrepancia documentada. No reescribir el checksum de migraciones aplicadas. Asignar el siguiente número solo tras confirmar el máximo y el formato; el SQL se aplica manualmente y se registra luego con checksum verificado, según `app/database/migrations.py`.

## Constitution Check after Design

- Separación de capas conservada: reglas de naturaleza, imputabilidad y cálculo de saldo en `domain`; coordinación y autorización en `application`; SQL en `adapters/persistence`; HTTP y esquemas en `adapters/api`.
- Ninguna lógica se traslada al frontend; API valida permisos, cuenta, plan, estado de periodo, balance e idempotencia.
- Migración aditiva; snapshots existentes no se transforman; tablas/triggers actuales de balance e inmutabilidad permanecen activos.
- Datasets del PCGE se versionan y verifican contra la fuente oficial antes de activar. No incluir utilidades tributarias ni exportación PLE.
- **Gate final: PASS CON PRECONDICIÓN**: migraciones, catálogo y reportes respetan la constitución. Resolver el estado de ledger antes de ejecutar la futura migración.

## Project Structure

### Documentation (this feature)

```text
specs/009-catalogo-cuentas-consultas-contables/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── accounting-catalog.openapi.yaml
```

### Source Code (repository root)

```text
app/
??? domain/accounting.py                  # Account, entry, and period rules
??? domain/accounting_reports.py          # Pure report calculations
??? application/accounting.py             # Plan, entry, and period use cases
??? application/accounting_reports.py     # Report orchestration
??? adapters/api/accounting.py            # ADMIN request/response contracts
??? adapters/persistence/accounting.py    # PostgreSQL persistence and queries
??? adapters/exports/accounting_reports.py # CSV/XLSX serialization
??? database/migrations.py                # Existing inspect/record-only migration ledger
sql/
??? migrations/                            # Additive schema and seed migrations after ledger reconciliation

tests/
??? unit/domain/
??? unit/application/
??? contract/
??? integration/
```

**Structure Decision**: Extender el módulo contable existente en las capas ya presentes. No añadir un servicio separado ni cambiar autenticación. La migración SQL debe seguir el formato `NNN_slug.sql` aceptado por `app/database/migrations.py`, después de resolver el registro actual; no fijar todavía el número de versión.

## Phase 0: Research

Completado en [research.md](research.md). Resuelve versión/fuente PCGE, compatibilidad de snapshots, semántica de periodos y reportes, exportación y el preflight de migraciones.

## Phase 1: Design & Contracts

Completado en [data-model.md](data-model.md), [contracts/accounting-catalog.openapi.yaml](contracts/accounting-catalog.openapi.yaml) y [quickstart.md](quickstart.md). Los artefactos definen el contrato futuro; todavía no se implementaron ni aplicaron.

## Release and migration sequencing

1. Reconcile the ledger/version 011 mismatch in a test environment before assigning the new migration number; compare the recorded checksum with the exact migration bytes. Do not revise checksums for already-applied SQL.
2. Add the chart/account/period tables and nullable references, then import the verified PCGE Modificado 2019 dataset as a versioned seed artifact. Validate account count, codes, names, parent links, account group, normal balance, and postable leaves against the MEF source and an accounting review.
3. Apply and verify the additive migration on an isolated database. Only after schema, seed counts, and preserved historical rows are checked, record its version/checksum via the existing explicit process.
4. Deploy backend contracts. During transition, the existing frontend payload may continue sending `account_code`/`account_name`; backend resolves the code exactly against the default plan and ignores client-supplied name. Invalid/unmatched codes are rejected. The separate frontend feature will send plan/account selection explicitly. Remove the compatibility shape only in a coordinated contract version.
5. Enable new entry validation and reports after seed verification; update the blank-schema reconstruction script to represent the new schema separately from the migration.

## Complexity Tracking

No hay excepciones a la constitución ni servicios nuevos. La complejidad adicional se limita a mantener reportes reconciliables, el PCGE versionado y compatibilidad histórica; es necesaria para los escenarios aceptados.
