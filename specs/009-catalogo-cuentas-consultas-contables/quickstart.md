# Quickstart: Validar catálogo y consultas contables

Esta guía se ejecuta cuando la implementación y la migración estén terminadas. Este plan no ejecuta pruebas ni aplica SQL. Usar solo una base de prueba verificada.

## Prerrequisitos

1. Backend y dependencias instalados según `README.md` y `requirements.txt`.
2. Base PostgreSQL de prueba `multiagentedb` con las tablas contables existentes y `schema_migrations` consultable.
3. Historial reconciliado: la versión `011` de inventario registrada y su archivo deben concordar en checksum; asignar la nueva versión contable después de confirmar el ledger real.
4. Migración contable aplicada manualmente a la base de prueba, esquema verificado y versión registrada con `app.database.migrations.py`. El dump de reconstrucción no cuenta como migración.
5. Dataset PCGE Modificado 2019 cargado desde la fuente MEF y validado en conteo, código, nombre, jerarquía, naturaleza y condición imputable.
6. Credencial de una cuenta ADMIN de prueba. No copiar secretos a comandos compartidos ni a trazas.

## Preparación del entorno

Desde el repositorio backend, seleccionar `DATABASE_URL` de la base de prueba en el archivo `.env` ignorado por Git y revisar el destino fuera de este documento. No ejecutar el siguiente comando hasta confirmar que apunta a prueba:

```powershell
python -m app.database.migrations status
```

Resultado esperado: la migración aplicada aparece como `RECORDED`; no debe haber `CHECKSUM_MISMATCH`, `UNRECORDED` no explicado ni `<archivo ausente>` sin resolver.

## Validación automatizada

Después de implementar los módulos de prueba planificados:

```powershell
python -m pytest tests/unit/domain/test_accounting.py tests/unit/application/test_accounting.py tests/contract/test_accounting_catalog_contract.py
```

Con la base PostgreSQL de prueba configurada y verificada:

```powershell
python -m pytest tests/integration/test_accounting_catalog_postgres.py tests/integration/test_accounting_api.py
```

Resultados esperados: reglas de jerarquía e imputabilidad pasan; cierres impiden asientos con fecha cerrada; reaperturas exigen motivo; reversión preserva cuenta y snapshot; saldos concilian; roles no ADMIN reciben 401/403; las rutas y tipos de descarga coinciden con `contracts/accounting-catalog.openapi.yaml`.

## Validación manual de contratos

1. Iniciar API: `python -m uvicorn app.main:app --reload`.
2. Con sesión ADMIN, listar planes y comprobar que el PCGE Perú Modificado 2019 está marcado predeterminado con fuente MEF. Consultar cuentas sin `q` y comprobar que devuelve una primera página ordenada por código; repetir con `q` parcial por código y denominación, junto a `status=ACTIVE` y `postable=true`, y revisar `total` e `items`.
3. Crear un plan alternativo y dos cuentas padre/hija; comprobar código duplicado, ciclo, cuenta padre imputable y escritura en periodo cerrado son rechazados.
4. Crear un asiento balanceado dentro de un periodo abierto con cuentas imputables del mismo plan; consultar detalle y verificar `account_id`, código/nombre snapshot y totales.
5. Crear una reversión y comprobar que el mayor y el diario presentan ambos asientos una vez y compensan los importes.
6. Consultar mayor y balance para un mismo rango. Revisar saldo inicial, débitos, créditos, saldo final y reconciliación.
7. Descargar diario, mayor y balance en CSV y XLSX con filtros idénticos; comparar columnas, filas, orden y totales con la respuesta JSON. Solicitar más del límite y comprobar error claro sin archivo truncado.
8. Cerrar un mes y comprobar que creación/reversión en ese mes falla; reabrir con motivo y verificar evento con actor/fecha.
9. Consultar los mismos recursos con una sesión no ADMIN y comprobar que no se entregan datos.
10. Revisar un asiento anterior a la migración: conserva sus IDs, líneas, importes y snapshots, y sus líneas aparecen marcadas como históricas/no vinculadas.

## Reconciliación de migración

No aplicar bootstrap sobre una base existente. Antes de ejecutar SQL, inspeccionar esquema y ledger; después de aplicar/verificar el script, registrar la versión correcta y volver a ejecutar `python -m app.database.migrations status`. Guardar el resultado de verificación según el procedimiento operativo del equipo, sin incluir la URL ni credenciales de base de datos.

