# Evidencia 14 — Ventas y armado PC flexible

## Cambios

- La herramienta de catálogo acepta términos naturales y busca de forma
  parametrizada en las columnas del inventario; devuelve opciones activas con
  stock y precio positivos.
- El supervisor acepta selección por número, nombre o característica y retiene
  artículos pendientes sin presentar SKU al cliente.
- Se agregaron perfiles RAG para oficina/estudio (7 componentes; usa gráficos
  integrados, sin GPU dedicada) y juegos (8 componentes con GPU). Al consultar
  la BD local se encontraron todos los componentes activos, con precio positivo
  y stock:
  - Oficina/estudio: componentes S/ 605.00; más mano de obra configurada de
    S/ 50.00, total observado S/ 655.00.
  - Juegos: componentes S/ 870.00; más mano de obra configurada de S/ 50.00,
    total observado S/ 920.00.
- La GPU del perfil de juegos requiere verificar dimensiones, conectores y
  consumo con la ficha del fabricante; no se declara compatibilidad completa.
- Los cambios de componente consultan alternativas por categoría, solicitan
  selección humana y producen una cotización nueva.
- Tras aceptación y logística, el nodo de cierre crea una garantía de tres
  meses para ventas y armado, asociada al ticket/cliente/cotización, y termina
  con despedida. La consulta previa por cotización y el bloqueo de fila hacen
  idempotente el registro.
- No se agregaron productos ni se ejecutaron escrituras en PostgreSQL local.

## Validación

Comando ejecutado:

```powershell
.\.venv-1\Scripts\python.exe -m pytest tests\test_hierarchical_workflows.py tests\test_multiagent_graph.py tests\test_repository.py tests\test_hierarchical_tracing.py -q
```

Resultado: **57 pruebas aprobadas**. Pylance no reportó problemas en los
archivos Python modificados y `git diff --check` no reportó errores.

## Limitaciones reales

- Los perfiles están acotados a nombres/códigos ya existentes y dependen del
  precio/stock de la BD en el momento de la consulta.
- El catálogo no aporta cotización fiable de proveedores ni suficientes datos
  para validar integralmente compatibilidad de cada GPU/placa/case; se expresa
  la revisión pendiente.
- La aceptación no descuenta ni reserva stock. El pago permanece `PENDING` y
  la logística `PENDING_RECEIPT`; esos estados se comunican en el cierre.
- La conexión local se usó solo para lecturas de catálogo/esquema, no para
  crear tickets, cotizaciones, pagos, registros logísticos ni garantías.

Checkpoint de commit del usuario: ____________________
