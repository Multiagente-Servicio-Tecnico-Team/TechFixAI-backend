# Quickstart: validar movimientos de inventario

## Prerrequisitos

- PostgreSQL de prueba con el esquema actual; aplicar primero la futura migración versionada en una BD descartable/restaurable.
- Backend de prueba iniciado; sesiones válidas `ADMIN` y `TECHNICIAN`, y cuenta `CUSTOMER` para verificar denegaciones.
- No ejecutar `contexto/tablas postgres v2.sql` para migrar ni usar producción en estas verificaciones.

La migración ya se aplicó en la base local de prueba `multiagentedb` (ledger `schema_migrations`, versión `011`). La verificación del corte confirmó 431 artículos, 2,618 unidades, 431 aperturas SYSTEM y preservación del movimiento legado. Aún falta recorrer los escenarios HTTP siguientes.

## Escenarios manuales

1. Crear un repuesto; verificar stock cero.
2. Registrar apertura con conteo, motivo e `Idempotency-Key`; verificar saldo, actor y movimiento `OPENING_BALANCE`.
3. Repetir misma clave/contenido: resultado replay, saldo/movimiento únicos. Misma clave con contenido distinto: conflicto.
4. Ajustar a conteo mayor y menor: delta entrada/salida calculado en backend. Igual conteo: sin movimiento.
5. Intentar conteo menor que reservas activas: conflicto sin mutación.
6. Recibir compra y confirmar venta: un movimiento por cada línea y saldo consistente.
7. Consultar movimientos por artículo, tipo, fechas y páginas; comprobar actor, motivo, origen y orden estable.
8. Verificar corte: filas históricas preservadas y apertura SYSTEM única por SKU, incluso si stock es cero. En la inspección de 2026-11-08 había 431 artículos, 2,618 unidades, un movimiento legado y cero reservas; no asumir esos conteos como fijos.
9. Sin sesión/CUSTOMER no debe poder modificar ni consultar; un artículo retirado permanece consultable en historial.
10. Forzar fallo transaccional en BD de prueba y confirmar que saldo y movimiento revierten juntos.

## Validación automatizada

No se agregaron ni ejecutaron pruebas automatizadas en este cambio. Los escenarios anteriores quedan como verificación manual para una fase de validación autorizada.

## Resultado esperado

Todo cambio posterior al corte se reconcilia desde su saldo inicial y movimientos. Los eventos previos se preservan como historia legado y no se duplican en el cálculo.

