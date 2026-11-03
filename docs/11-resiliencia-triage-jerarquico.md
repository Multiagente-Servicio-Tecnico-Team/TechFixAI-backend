# Evidencia 11 — resiliencia del triage jerárquico

## Hallazgo

La reproducción con Groq devolvió una ruta `service` válida, pero sin título o
descripción. El supervisor rechazaba la salida mediante `ValueError`; la API la
convertía en HTTP 502. El mensaje `Provider error details redacted.` en LangSmith
es la redacción configurada para los detalles de errores, no el diagnóstico de
la causa raíz.

## Cambio

- El prompt pide explícitamente ambos campos en la ruta de servicio.
- Un título vacío o ausente usa `Solicitud de atención`.
- Una descripción vacía o ausente se recupera del último mensaje de cliente.
- Si no hay un mensaje de cliente utilizable, se solicita aclaración antes de
  crear el ticket.

## Validación

- Prueba de regresión local con salida estructurada incompleta: verifica que el
  ticket conserva el mensaje original como descripción y no lanza `ValueError`.
- Ejecución real del grafo jerárquico con Groq: completó el triage y el
  diagnóstico con `outcome=awaiting_confirmation` y `route=service`.
- `POST /api/chat` con el grafo real, un guard aislado y repositorio de prueba
  respondió HTTP 200 con el patrón jerárquico y una respuesta no vacía.
- Para la ejecución real, el repositorio fue sustituido por un doble de prueba;
  no se escribieron tickets en PostgreSQL. LangSmith se habilitó con
  `LANGSMITH_HIDE_INPUTS=true` y `LANGSMITH_HIDE_OUTPUTS=true` solo durante la
  prueba; no se cambió `.env`.
- La primera repetición del grafo se detuvo antes de llamar al modelo porque el
  harness no incluía `configurable.thread_id`; la ejecución repetida con la
  configuración usada por la API sí completó correctamente.

## Alcance pendiente

- La API con cookie de sesión real y PostgreSQL no se ejecutó; la comprobación
  HTTP usa un guard de prueba.
- Las trazas de producción deben mantener el ocultamiento de inputs/outputs.
- Checkpoint de commit del usuario: ____________________.
