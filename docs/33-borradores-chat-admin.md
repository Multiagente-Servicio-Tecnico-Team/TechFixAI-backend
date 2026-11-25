# Borradores conversacionales para operaciones ADMIN

## Flujo

Cuando el modelo identifica una escritura, entrega la capacidad y los argumentos que pudo extraer. `AdminCapabilityService.prepare()` valida contra el mismo esquema Pydantic que usa la ruta operativa. Si faltan datos requeridos o sus valores no cumplen el esquema, el chat conserva los argumentos parciales y pregunta por los nombres de campo faltantes o inválidos; no prepara una escritura todavía.

La respuesta del ADMIN se analiza con el contexto del borrador activo. Los nuevos campos se combinan con los ya recopilados, incluidos los campos de cada línea, y se ejecuta de nuevo la validación. Si aún hay problemas, el asistente vuelve a preguntar. Cuando el esquema queda válido, el sistema genera la propuesta visual normal y exige confirmación explícita antes de llamar a `execute()`.

## Formatos, opciones y referencias

El LLM interpreta el lenguaje y propone valores; no es la autoridad de validación. El backend aplica los modelos Pydantic y las reglas de negocio de la API antes de mostrar la propuesta. Si un campo falla, la aclaración identifica el campo, explica el motivo e indica un formato de ejemplo o los valores enumerados que admite el sistema. Para campos vinculados, el backend comprueba que el cliente, proveedor, producto, línea, categoría, cuenta contable del plan seleccionado o registro exista y corresponda a la operación. Si no, solicita corregir esa referencia.

Los datos correctos se mantienen en el borrador mientras el ADMIN corrige el campo rechazado. La validación se repite en cada respuesta; decir «continuar» o confirmar no omite un error. No se crea una propuesta ni se ejecuta una escritura mientras quede un error. Para asientos contables también se verifica antes de proponer que el plan esté activo y cada cuenta sea imputable y vigente a la fecha del asiento. Correos: se valida la sintaxis y se pasa el dominio a minúsculas; se conserva la parte local y no se comprueba que el buzón exista. Teléfonos de clientes y tickets: nueve dígitos peruanos, con separadores opcionales y prefijo `+51`; teléfonos de proveedores: entre 7 y 15 dígitos para admitir formatos internacionales.

## Estado y aislamiento

`PendingAdminDraft` guarda capacidad, argumentos parciales, campos pendientes, necesidad de corregir valores y vencimiento. Está adjunto a la conversación, que ya está vinculada al actor autenticado, rol y patrón. Un borrador vence a los cinco minutos; la expiración se aplica cuando se vuelve a usar la conversación. «Cancelo» lo descarta. Una consulta o escritura claramente distinta también lo descarta sin efectos de negocio. Confirmar mientras aún faltan campos solo vuelve a pedirlos.

Los borradores viven en memoria del proceso, igual que las propuestas ADMIN actuales. Reinicios o solicitudes que lleguen a otra instancia pueden perderlos; en ese caso hay que volver a formular la operación. No se agregó tabla ni migración. Texto y audio usan el mismo `conversation_id` y la misma lógica de validación.

## Límites

El LLM sigue interpretando lenguaje natural y puede no identificar una operación ambigua. Si no determina la capacidad, conserva la respuesta general de ayuda; no se crea un borrador sin una operación reconocible. El esquema del backend es quien decide si los datos bastan, y ninguna aclaración ejecuta el cambio. La frase de confirmación solo aplica después de presentar una propuesta completa.

Requisitos: FR-024 y FR-025 en `specs/011-chat-multirole-patrones/spec.md`. Guion paso a paso: `docs/31-guia-pruebas-admin-por-voz.md`.
