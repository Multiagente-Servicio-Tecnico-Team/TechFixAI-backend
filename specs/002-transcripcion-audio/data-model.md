# Data Model: Transcripción de audio para el chat

El audio no introduce entidades persistentes ni cambios en PostgreSQL. Los siguientes objetos representan datos temporales de una petición y la transcripción que se entrega al turno de chat.

## AudioSubmission

Representa una grabación recibida en `POST /api/chat/audio`.

| Campo | Tipo | Reglas |
|---|---|---|
| `audio` | archivo/binario | Obligatorio; tamaño entre 1 byte y 25.000.000 bytes; el MIME/extensión debe pertenecer a los formatos admitidos por Groq. Se cierra al terminar la petición. |
| `duration_ms` | entero | Obligatorio; valor entre 1 y 120.000, medido por el navegador. El frontend detiene automáticamente la grabación al alcanzar 120 s. |
| `pattern` | enum | `hierarchical`, `orchestrator` o `decentralized`; requerido por el cliente para mantener su selección actual. |
| `conversation_id` | UUID o nulo | Si se omite, el caso de uso crea una conversación como `SendChatMessage`; si se envía, debe pertenecer al cliente y al mismo patrón. |
| `request_id` | UUID | Obligatorio; idempotencia por cliente. Una clave exitosa solo se puede reusar con la misma huella de audio y metadatos. |
| `customer_id` | entero | Derivado exclusivamente de `techfix_session`; nunca se toma del cuerpo multipart. |

`duration_ms` sirve para validar el flujo normal de grabación del navegador; no es una defensa contra clientes HTTP manipulados. El límite de bytes, el MIME y la cuota por cliente se validan en backend antes de llamar a Groq.

## Transcription

Resultado temporal de `AudioTranscriber`.

| Campo | Tipo | Reglas |
|---|---|---|
| `text` | string | Texto no vacío tras normalizar espacios; longitud máxima de 2.000 caracteres para coincidir con `ChatIn.message`; no truncar. |

No conservar nombre de archivo, bytes de audio ni segmentos. El adaptador interpreta temporalmente `no_speech_prob` y rechaza el resultado si no hay segmentos o todos tienen valor >= 0.6; el caso de uso solo recibe texto normalizado. No enviar texto o audio a trazas.

## AudioChatRequestRecord

Registro efímero para reintentos de red.

| Campo | Tipo | Reglas |
|---|---|---|
| `customer_id` | entero | Parte del ámbito de idempotencia. |
| `request_id` | UUID | Clave enviada por el frontend. |
| `payload_fingerprint` | SHA-256 | Huella de audio y parámetros, no permite reconstruir el archivo. |
| `response` | `AudioChatOut` | Solo respuesta exitosa; se conserva hasta 10 minutos para devolverla ante reintento idéntico. |
| `state` | `in_progress` o `completed` | Reclamo atómico para evitar dos transcripciones/turnos simultáneos por la misma clave. Fallos liberan la clave y no quedan cacheados. |

El registro reside en memoria del proceso y se purga al expirar; no es una fuente de verdad durable ni requiere migración.

## ChatTurn existente

Se crea o actualiza usando el flujo normal. La conversación ya posee cliente y patrón inmutables; la respuesta existente conserva `conversation_id`, `reply`, `pattern` y los datos opcionales `quote` y `ticket`. El DTO de audio agrega `transcript` para mostrar el mensaje del cliente.

## Estados de interacción (frontend)

```text
idle -> recording -> submitting -> complete
  \-> permission_denied
  \-> unsupported_capture
  \-> transcription_error -> idle
```

El botón solo inicia en `idle`; el segundo toque finaliza `recording`. En `submitting` queda deshabilitado para evitar envíos concurrentes. Los errores muestran una explicación y permiten reintentar o usar texto.
