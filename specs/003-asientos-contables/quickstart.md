# Quickstart: validar asientos contables backend

Este quickstart documenta cómo migrar y validar la API backend. Se ejecutó en la base PostgreSQL de prueba identificada durante esta implementación; los datos sintéticos creados se enumeran en `docs/21-asientos-contables.md`.

## Prerrequisitos

1. Entorno Python del backend instalado con los requirements del repositorio.
2. Una base PostgreSQL de **prueba**, nunca producción, creada con el esquema ampliado requerido por el proyecto. Configurar `ACCOUNTING_TEST_DATABASE_URL` explícitamente; la fixture contable nunca usa `DATABASE_URL` ni carga `.env`.
3. Una cuenta activa `ADMIN` autenticable y una cookie de sesión emitida por `/auth/login`.
4. La migración contable aplicada solo a esa BD de prueba.
5. OpenAPI: [accounting.openapi.yaml](contracts/accounting.openapi.yaml).

## Comprobación de esquema

Antes de migrar, verificar base/entorno sin mostrar credenciales, comparar nombres/tablas existentes y confirmar que no se aplicó previamente. Aplicar la migración versionada en una operación revisable con `ON_ERROR_STOP`; guardar evidencia de estado anterior y posterior. Confirmar que se crearon catálogo, entradas, líneas, auditoría, índices/constraints y seis categorías iniciales; que no se alteraron `users`, pagos, cotizaciones ni el inventario.

La migración es aditiva; nunca sustituirla por `sql/creacion_tablas_ingles_sin_inserciones.sql`, que recrea el esquema. Desde PowerShell, primero confirmar el destino de forma segura y después aplicar solo con la variable explícita:

```powershell
if (-not $env:ACCOUNTING_TEST_DATABASE_URL) { throw 'Configura ACCOUNTING_TEST_DATABASE_URL con la BD de prueba.' }
psql "$env:ACCOUNTING_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT current_database() AS database_name, current_user AS database_user;"
# Verifica que database_name corresponde a la BD desechable de pruebas antes de seguir.
psql "$env:ACCOUNTING_TEST_DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/migrations/003_accounting_entries.sql
```

La aplicación no lee ni sustituye esta variable por `DATABASE_URL`. No ejecutar el comando si el nombre de BD no se ha confirmado como entorno de prueba.

## Pruebas automatizadas

```powershell
python -m pytest tests/unit/domain/test_accounting.py tests/unit/application/test_accounting.py -q
python -m pytest tests/unit/adapters/test_accounting_repository.py tests/contract/test_accounting_contract.py -q
python -m pytest tests/integration/test_accounting_api.py -q
python -m pytest tests/integration/test_accounting_postgres.py -q
```

La integración PostgreSQL es la única que demuestra migración, trigger de balance diferido, rollback, secuencia concurrente e índices. No ejecutar las pruebas de escritura contra una base compartida o de producción.

## Flujo HTTP de aceptación

1. Sin cookie: `GET /api/admin/accounting/categories` → `401`.
2. Con cookie de `CUSTOMER` o `TECHNICIAN`: listado y creación → `403`.
3. Con cookie `ADMIN`: consultar categorías; `GET /api/admin/accounting/entries` → `200` y listado vacío/paginado.
4. Crear con `POST /api/admin/accounting/entries`, encabezado `Idempotency-Key` UUID y dos o más líneas balanceadas → `201`, estado `CONFIRMED`, correlativo, actor de sesión, importes como cadenas.
5. Repetir igual actor/key/body → mismo asiento, sin nueva fila. Reusar key con otro body → `409`.
6. Crear un asiento desbalanceado o con una línea con ambos lados positivos → `422`; verificar que no quedan filas parciales.
7. `GET /api/admin/accounting/entries/{id}` → encabezado, líneas, debe/haber, total resumen, categoría, responsable y eventos.
8. `POST /api/admin/accounting/entries/{id}/reverse` con fecha y razón → nuevo asiento con debe/haber intercambiados, status original `REVERSED`, enlaces/eventos; segundo intento → `409`.
9. Forzar un error entre inserciones en una prueba aislada → verificar rollback de encabezado, líneas y eventos.
10. Confirmar `git diff --check`, suite aislada afectada, `python -m compileall app` y `python -m pytest` según configuración de tests del repo.

## Verificación de salida

- El detalle devuelto corresponde campo por campo a lo que consume el futuro frontend; no se hacen cambios de interfaz en este repo.
- Ninguna petición no `ADMIN` puede leer datos, crear o revertir.
- La feature no registra pagos/cobros automáticamente, no actualiza asientos existentes y no presenta archivos PLE a SUNAT.


La migraci?n se aplic? en `multiagentedb` tras verificar que era la base de prueba autorizada. El inventario pas? de 15 tablas/30 ?ndices a 19 tablas/46 ?ndices; se agregaron las cuatro tablas contables y seis categor?as. Las pruebas PostgreSQL terminaron con 4 aprobadas y el smoke test HTTP verific? creaci?n, replay idempotente, detalle, reversi?n, validaci?n y autorizaci?n. Los registros sint?ticos persistentes y sus IDs est?n descritos en `docs/21-asientos-contables.md`; la BD ya no est? vac?a para esta feature.

## Resultado ejecutado (2026-11-02)

La migracion se aplico en `multiagentedb` tras verificar que era la base de prueba autorizada. El inventario paso de 15 tablas/30 indices a 19 tablas/46 indices; se agregaron las cuatro tablas contables y seis categorias. Las pruebas PostgreSQL terminaron con 4 aprobadas y el smoke test HTTP verifico creacion, replay idempotente, detalle, reversion, validacion y autorizacion. Los registros sinteticos persistentes y sus IDs estan descritos en `docs/21-asientos-contables.md`; la BD ya no esta vacia para esta feature.
