# 01 — Ventas del patrón jerárquico

El supervisor comercial deriva consultas de venta directa a almacén y ventas.
El catálogo `spare_parts` es la fuente de stock y precio; `Decimal` se usa para
calcular los importes. El pago solo se crea como `PENDING` después de aceptar la
propuesta. La preferencia de retiro/courier queda como `PENDING_RECEIPT` y no se
presenta como pago, reserva o entrega confirmados.

Para `REPAIR` y `SUPPORT`, el triage registra primero el ticket como `NEW`. Tras
RAG y diagnóstico técnico, el mismo ticket guarda `diagnosis_type` y el campo
`hardware_diagnosis` o `software_diagnosis`, y pasa a `IN_DIAGNOSIS`. Aceptar la
cotización registra `quotes` como `ACCEPTED`, los detalles disponibles, el pago
como `PENDING` y el ticket como `PAYMENT_PENDING` dentro de una transacción.
Rechazarla cancela el ticket sin crear cotización ni pago.

## Casos cubiertos

- Venta directa por nombre/categoría, con búsqueda parametrizada del catálogo,
  stock/precio positivos y selección por nombre o número sin exponer SKU.
- Las preguntas por modelos/precios actuales de procesadores se consideran
  consultas de catálogo, no FAQ de memoria; se muestran únicamente los modelos
  que devuelve PostgreSQL y se espera la selección/aceptación del cliente.
- Solicitud de selección explícita si hay varias coincidencias; las solicitudes
  con varios productos conservan la cola mientras se selecciona cada uno.
- Armado PC mediante perfiles RAG para oficina/estudio y gaming, condicionados a
  inventario, precio, presupuesto y revisión de compatibilidad documentada.
- Cambios de componentes antes de aceptar, con selección por nombre/número y
  recálculo de la cotización con precios actuales y `Decimal`.
- Rechazo de propuesta: cancela el ticket de ingreso y no crea cotización ni pago.
- Aceptación con cotización, detalle y pago pendiente en transacción.
- Actualización idempotente de modalidad logística mientras la recepción sigue
  pendiente; no se permite cambiarla después de la recepción.
- Diagnóstico técnico guardado en el ticket de ingreso, en
  `hardware_diagnosis` o `software_diagnosis` según `diagnosis_type`.
- Aceptación de reparación/soporte con cotización aceptada y pago pendiente en
  transacción; tickets de ingreso ya existentes no se duplican.
- Cierre posterior a logística para venta y armado: póliza idempotente de tres
  meses enlazada al cliente, ticket y cotización, seguida de despedida.
- La clasificación tolera que el proveedor estructurado devuelva
  `required_parts: null` y lo normaliza a una lista vacía. La clasificación y
  el diagnóstico usan JSON mode con esquema incluido en el prompt y validación
  local Pydantic, para que la normalización ocurra antes del flujo y no durante
  la validación remota de tool calls de Groq.
- Tarifa predeterminada de mantenimiento/reparación alineada a S/ 35.00 de los
  prompts de servicio. `LABOR_MAINTENANCE_PRICE` sigue permitiendo configurar
  explícitamente otra tarifa.

## Limitaciones del esquema confirmado

- El catálogo no define toda la compatibilidad entre piezas. Los perfiles usan
  compatibilidades declaradas en descripciones disponibles, pero dimensiones,
  conectores y consumo de GPU/PSU o BIOS pueden requerir validación del fabricante.
- No hay relación de producto/proveedor ni oferta de proveedor, por lo que
  compras no inventa precios o plazos.
- La póliza de venta/armado se registra al final del flujo indicado por el patrón
  tras registrar logística; no confirma que el pago, la recepción o la entrega
  estén completados.
- Un pedido aceptado no descuenta ni reserva existencias.

## Validación

Suite aislada enfocada en repositorio, workflows jerárquicos, grafo, API y
trazabilidad y configuración: **60 pruebas aprobadas**. La conexión a PostgreSQL
local confirmó las columnas `diagnosis_type`, `hardware_diagnosis` y
`software_diagnosis`; no se realizaron escrituras reales. Para reproducir la suite:

```powershell
$env:HIERARCHICAL_TRACE_PATH = Join-Path $env:TEMP 'hierarchical-traces-test.jsonl'
.\.venv-1\Scripts\python.exe -m pytest tests/test_repository.py tests/test_hierarchical_tracing.py tests/test_hierarchical_workflows.py tests/test_multiagent_graph.py tests/test_pattern_api.py tests/test_settings.py -q
Remove-Item -LiteralPath $env:HIERARCHICAL_TRACE_PATH
```

Checkpoint de commit del usuario: ____________________
