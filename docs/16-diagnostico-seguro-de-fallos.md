# Evidencia 16 — fallo de retiro y diagnóstico seguro

## Hallazgo de la interacción

La traza local `.local/hierarchical-traces.jsonl` muestra que `logistics_agent`
y la herramienta `logistics_record_write` terminaron correctamente. El error
ocurrió después, en `order_completion_agent`, durante `warranty_write`, que
registra la garantía de tres meses. La excepción original no se guarda en el
JSONL y LangSmith la reemplaza deliberadamente con `Provider error details
redacted.`; por ello no se puede reconstruir el SQLSTATE de esa ejecución a
partir de la traza existente.

La introspección de solo lectura confirmó las columnas de `warranties`, los
enum de `SALE`, `PC_BUILD` y `ACTIVE`, y que la expresión de fecha de garantía
funciona en PostgreSQL. No se modificaron tickets, cotizaciones, logística ni
garantías durante esta revisión.

## Cambio de diagnóstico

- Los eventos locales `error` de nodos y herramientas incluyen el tipo de
  excepción y un SQLSTATE validado cuando está disponible.
- El backend localiza esos eventos por execution ID en
  `.local/hierarchical-traces.jsonl`.
- Los logs del proceso API registran el tipo y SQLSTATE, sin texto de excepción.
  En despliegue, revisar los logs del servicio en el proveedor de hosting.
- LangSmith y la respuesta al cliente siguen ocultando detalles internos.

## Validación

- `tests/test_hierarchical_tracing.py` y `tests/test_hierarchical_workflows.py`:
  13 aprobadas. Las pruebas se ejecutaron con LangSmith desactivado y no
  escribieron en PostgreSQL.
- `git diff --check` limpio.

## Límite

El fallo ya ocurrido solo conserva el nodo/herramienta fallidos; el tipo y
SQLSTATE no se registraban entonces. Si el cliente vuelve a intentar el retiro
y falla de nuevo con el backend actualizado, consultar el nuevo evento `error`
y el log del backend para obtener el SQLSTATE.
