# Research: Catálogo de cuentas y consultas contables

**Feature**: `009-catalogo-cuentas-consultas-contables`

## Decision 1: PCGE de referencia

**Decision**: Usar el **Plan Contable General Empresarial Modificado 2019** como primera versión del plan Perú, guardando edición, jurisdicción, fuente y vigencia como metadatos del plan. Mantener la declaración de que es una herramienta interna y no una certificación tributaria.

**Evidence**: La página oficial del MEF para PCGE lista el “Plan Contable General Empresarial Modificado 2019”; el MEF también aloja el PDF completo y la Resolución CNC Nº 002-2019-EF/30, que aprobó el plan.

**Rationale**: Da una versión concreta y verificable en vez de inferir el catálogo desde copias o conocimiento del modelo. Permite que cambios futuros se publiquen como otra edición/plan sin sobrescribir asientos anteriores.

**Alternatives considered**:
- Cargar un PCGE de 2010: descartado como opción inicial porque la página oficial lista el plan modificado 2019.
- Importar cuentas desde un repo de terceros: descartado por procedencia menos verificable.
- Llamar al plan “SUNAT” o prometer conformidad PLE: descartado; un catálogo de cuentas no implementa las obligaciones y formatos de libros electrónicos.

**Sources**:
- [MEF — Plan Contable General Empresarial - PCGE](https://www.mef.gob.pe/es/contabilidad-publica-sp-6700/388-documentacion/6127-plan-contable-general-empresarial-pcge)
- [MEF — PCGE Modificado 2019 (PDF)](https://mef.gob.pe/contenidos/conta_publ/pcge/PCGE_2019.pdf)
- [MEF — Resolución CNC 002-2019-EF/30](https://www.mef.gob.pe/es/contabilidad-publica-sp-6700/57-consejo-normativo-de-contabilidad/1383-resoluciones-del-consejo-normativo-de-contabilidad)

## Decision 2: Historial y migraciones PostgreSQL

**Decision**: Ampliar las tablas actuales de forma aditiva: nuevos planes/cuentas, asociación opcional de líneas históricas a cuentas y referencia opcional del encabezado a un plan. Conservar `account_code`, `account_name`, fechas, importes, estados y relaciones actuales. No intentar convertir códigos históricos por coincidencia de texto.

**Evidence inspected**:
- `sql/esquema-vacio-produccion.sql` incluye las tablas `accounting_entries`, `accounting_entry_lines`, `accounting_categories` y `accounting_audit_events`; las líneas requieren código/nombre textual, debe y haber.
- `app/adapters/api/accounting.py` acepta actualmente `account_code`/`account_name` desde la solicitud.
- `app/adapters/persistence/accounting.py` persiste esos valores, devuelve snapshots y los copia al crear la reversión.
- `sql/migrations/` contiene en este checkout `20261108_inventory_movement_traceability.sql`, pero no la migración histórica `003_accounting_entries.sql`. El dump de esquema y `contexto/tablas postgres v2.sql` son snapshots/bootstrap, no migraciones.
- `app/database/migrations.py` reconoce solamente nombres `NNN_slug.sql`, inspecciona checksums y registra cambios después de que el operador aplica y verifica el SQL; no ejecuta migraciones.
- `sql/migrations/README.md` indica que inventario quedó registrado como versión `011`, pero el nombre actual del archivo de inventario no cumple el patrón que inspecciona `migrations.py`.

**Rationale**: La migración puede preservar toda evidencia y hacer reportables las líneas no vinculadas. El libro de versiones debe reconciliarse antes de escoger otro número o registrar un checksum; ni los dumps ni una consulta indirecta prueban el estado de cada entorno.

**Alternatives considered**:
- Convertir automáticamente líneas existentes que coincidan por código/nombre: descartado; puede enlazar a otra edición/cuenta y cambia el significado histórico.
- Modificar o reemplazar el esquema mediante el script bootstrap: descartado para bases con datos; el README de migraciones prohíbe tratar bootstrap como upgrade.
- Ejecutar SQL automáticamente al iniciar la API: descartado; `migrations.py` está diseñado como inspección y registro explícito.

**Implementation preflight**: inspeccionar ledger y checksums del entorno de prueba autorizado. Reconciliar el nombre/versionado del archivo `011` preservando los bytes y checksum ya aplicados; si la evidencia no coincide, resolver hacia adelante y elegir la siguiente versión disponible tras la verificación. No cambiar archivos históricos que ya fueron aplicados.

## Decision 3: Catálogo y asientos

**Decision**: Un plan tiene edición propia, una lista jerárquica y estado. Solo una cuenta activa, vigente e imputable puede recibir nuevas líneas. El plan de cada asiento nuevo y la cuenta de cada línea se validan en el backend. Se mantienen snapshots obligatorios del código y nombre en cada línea confirmada.

**Rationale**: La referencia permite agrupar por cuenta y validar valores, mientras que el snapshot conserva cómo se registró cada asiento aunque cambie la descripción futura.

**Alternatives considered**:
- Reemplazar snapshots con joins al nombre actual: descartado porque cambiaría los detalles históricos al renombrar cuentas.
- Guardar texto libre sin FK para nuevos asientos: descartado porque conserva la fragmentación que origina esta feature.
- Eliminar cuentas inactivas: descartado si ya están usadas; se desactivan o se publica otra edición.

## Decision 4: Periodos y reversión

**Decision**: Periodos mensuales por año/mes y estado OPEN/CLOSED. Cerrar/reabrir es una transición ADMIN auditada, con razón obligatoria al reabrir. La fecha operativa de un asiento o reversión debe pertenecer a mes abierto. La reversión continúa siendo un nuevo asiento compensatorio vinculado al original y nunca reabre un mes automáticamente.

**Rationale**: Mantiene la inmutabilidad existente, evita escrituras en periodos cerrados y deja una pista explícita cuando se autoriza modificar de nuevo un periodo.

**Alternatives considered**:
- Reescribir/borrar asientos al cerrar: descartado; contradice las reglas actuales de inmovilidad.
- Reabrir automáticamente para revertir: descartado porque el cierre es una decisión auditada.
- Usar periodos trimestrales/anuales: descartado por la decisión ya confirmada de periodos mensuales.

## Decision 5: Semántica de reportes

**Decision**:
- **Diario**: movimientos línea por línea en orden estable por fecha de operación y correlativo; incluye asientos originales y reversiones.
- **Mayor**: movimientos de una cuenta, saldo inicial anterior al rango, débito/crédito y saldo corrido. Para cuentas catalogadas, usar su lado normal; para legacy sin cuenta vinculada, mostrar débito menos crédito y señalar que no tiene naturaleza conocida.
- **Balance de comprobación**: por cuenta, saldo inicial, débitos, créditos y saldo final del rango; las reversiones compensan y no se omiten por el estado `REVERSED` del original.

**Rationale**: Las consultas deben derivar de la misma población contable y mostrar las reversiones como evidencia. Evita que un filtro por estado quite los dos lados de una reversión.

**Alternatives considered**:
- Excluir originales revertidos: descartado; falsea actividad histórica y quiebra el saldo.
- Reportar únicamente las líneas ligadas al plan: descartado porque oculta los asientos existentes que no se deben mapear automáticamente.
- Tratar naturaleza de legacy como conocida según el primer dígito: descartado porque no hay fuente de catálogo que valide ese dato histórico.

## Decision 6: Exportaciones

**Decision**: CSV con la biblioteca estándar de Python; XLSX con `openpyxl` en modo write-only. Ambos reciben el mismo iterador de filas ya filtradas y ordenadas, respetan el mismo esquema de columnas/totales y tienen un límite inicial de 10 000 filas.

**Evidence**: La documentación oficial de `openpyxl` describe el modo write-only para escritura secuencial con uso de memoria casi constante y permite generar archivos grandes sin mantener cada celda en memoria.

**Rationale**: No añadir una dependencia tabular grande como Pandas para tres reportes. La salida XLSX se resuelve con una dependencia acotada; CSV no requiere paquete extra.

**Alternatives considered**:
- Pandas: descartado por peso y porque no aporta valor a la lógica de reportes.
- Construir XLSX a mano con ZIP/XML: descartado por complejidad y fragilidad.
- Truncar silenciosamente: descartado; superar el límite debe producir error claro para acotar el rango.

**Source**: [openpyxl — Optimised Modes](https://openpyxl.readthedocs.io/en/stable/optimized.html)

## Decision 7: Autorización y capa de responsabilidad

**Decision**: Reusar autorización ADMIN y autenticación actuales. Reglas de cuenta, periodo y totales pertenecen al dominio/aplicación; SQL a persistencia; serialización de CSV/XLSX y contratos HTTP a adapters. No crear contabilidad automática desde pagos, ventas o compras.

**Evidence**: `specs/003-asientos-contables/spec.md`, `app/adapters/api/accounting.py`, `app/application/accounting.py`, `app/domain/accounting.py`.

**Rationale**: Amplía la capacidad contable existente sin cambiar el mecanismo de login ni mezclar operaciones comerciales con asientos internos.

## Resolved technical unknowns

- PCGE: resuelto a PCGE Modificado 2019 del MEF.
- XLSX: resuelto a `openpyxl` write-only; dependencia nueva.
- Migraciones: el formato del nuevo script debe ser `NNN_slug.sql`, pero la siguiente versión no se fija hasta reconciliar el ledger real.
- Runtime de Python: el repo no contiene `runtime.txt`, `.python-version` ni `pyproject.toml`; el plan no fija una versión nueva. El entorno de despliegue debe confirmarse y mantener compatibilidad con dependencias actuales antes de release.
