# Respuestas estructuradas del chat ADMIN

## Objetivo

El chat ADMIN entrega una frase breve para la conversación y, por separado, una representación tipada para mostrar los datos de la operación. La interfaz no debe convertir el objeto `result` en texto JSON visible.

## Contrato

`POST /api/admin/chat` y `POST /api/admin/chat/audio` conservan `reply`, `proposal` y `result`, y agregan `presentation` cuando hay información que mostrar:

- `table`: `title`, `summary`, `columns`, `rows` y `empty_message` para resultados de consultas.
- `record`: `title`, `fields` con etiquetas/valores y `sections` anidadas para detalles.
- `list`: elementos legibles en una lista.
- `download`: etiqueta y URL de un reporte.

Una propuesta incorpora `summary`, `values` y su propia `presentation`. `reply` solo guía al ADMIN para revisar, confirmar o cancelar. El resultado confirmado llega en `result` y también en `presentation`; la UI renderiza esta última.

## Presentación en el frontend

`TechFixAI-frontend/src/features/chat/AdminChatPresentation.jsx` muestra campos como pares etiqueta/valor, listas como viñetas, resultados tabulares en una tabla con desplazamiento horizontal y exportaciones como enlace de descarga. `AdminChat.jsx` conserva los botones de confirmar/cancelar en la tarjeta de propuesta. Los textos se renderizan mediante React, sin insertarlos como HTML.

Como compatibilidad, si un backend devuelve `result` pero todavía no incluye `presentation`, `AdminChat.jsx` construye una tabla básica a partir de `result.items` o un detalle a partir de campos simples. Así las consultas siguen mostrando datos durante un despliegue escalonado.

El backend limita las tablas a 50 filas y 7 columnas, y los detalles a 30 campos por registro para mantener legible el panel. Los valores monetarios se muestran en PEN cuando el campo representa un importe. El objeto crudo `result` se conserva para clientes API que necesiten procesarlo, pero no se debe mostrar directamente en el chat.

## Revisión

La especificación y el OpenAPI canónicos están en `specs/011-chat-multirole-patrones/`. No se ejecutaron pruebas automatizadas, build ni validación manual del navegador en esta actualización.
