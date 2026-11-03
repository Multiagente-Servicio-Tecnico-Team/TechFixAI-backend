# Implementation Plan: Transcripción de audio para el chat

**Branch**: `002-transcripcion-audio` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-transcripcion-audio/spec.md`

## Summary

Agregar una entrada de voz al chat existente: un toque inicia la grabación y el siguiente la detiene y envía. Un puerto de aplicación solicita la transcripción a Groq `whisper-large-v3-turbo`; si resulta válida, el caso de uso reutiliza `SendChatMessage` para que el texto recorra la conversación y el patrón activos. El texto escrito conserva su contrato y comportamiento. No se guarda audio ni se modifica PostgreSQL.

El backend expone un endpoint multipart autenticado y devuelve la transcripción junto con la respuesta normal del chat. La interfaz React vive en `../TechFixAI-frontend`, como repositorio Git separado pero disponible en el workspace.

## Technical Context

**Language/Version**: Python 3.12; frontend existente React + Vite (repositorio separado).

**Primary Dependencies**: FastAPI 0.142.2, LangGraph 1.2.2, Groq SDK 0.37.1 ya listado en `requirements-agent.txt`, Pydantic 2.13.5; añadir `python-multipart` para recibir `multipart/form-data`.

**Storage**: Sin almacenamiento nuevo. Conversación y resultado conservan la política actual en memoria; el archivo se mantiene solo durante la petición y se cierra al terminar.

**Testing**: pytest 8.4.2; pruebas unitarias con `AudioTranscriber` falso, pruebas de contrato del endpoint y de los tres patrones, integración FastAPI/TestClient con sesión y proveedor simulado, y validación manual en el frontend React externo.

**Target Platform**: API FastAPI en Render y navegador con micrófono disponible bajo HTTPS o localhost; frontend React + Vite publicado en Vercel según `README.md`.

**Project Type**: Backend web-service con frontend web mantenido en otro repositorio.

**Performance Goals**: Tiempo máximo de espera de transcripción: 30 segundos; la ruta devuelve el resultado o un error temporal al alcanzar ese límite. No se fija un SLA p95 del proveedor antes de medirlo en el entorno desplegado.

**Constraints**: `whisper-large-v3-turbo`; idioma `es`; audio de hasta 120 segundos y 25.000.000 bytes; hasta 5 transcripciones por minuto y cliente autenticado; formatos admitidos por Groq. El navegador detiene la grabación a los 120 segundos; el backend limita el tamaño de la petición multipart de forma incremental y valida el MIME y el campo de duración declarado. La bandera `AUDIO_TRANSCRIPTION_ENABLED` queda desactivada por defecto. Mensajes, credenciales y audio no se incluyen en logs ni trazas. El límite de 25 MB se elige por debajo del más conservador de los valores publicados por Groq; el proveedor factura un mínimo de 10 segundos por petición de audio.

**Scale/Scope**: Una petición contiene una sola grabación breve y produce como máximo un turno. Aplicación y conversaciones ya son de estado local al proceso; idempotencia de audio tendrá el mismo alcance de una instancia. No cubre streaming, historial de audio, transcripción por lotes, traducción, otros proveedores ni cambios en base de datos.

## Constitution Check

### Gates antes del diseño

| Gate | Resultado | Evidencia |
|---|---|---|
| Reglas de negocio compartidas | PASS | Una transcripción normalizada entra a `SendChatMessage`; no se replica lógica dentro de los patrones. |
| Persistencia autorizada | PASS | Audio temporal; el caso de uso normal conserva sesión, dueño y patrón bloqueado. |
| Evidencia antes que invención | PASS | Si el proveedor falla o no devuelve texto, no se invoca ningún patrón. |
| Seguridad y privacidad | PASS | Cookie de sesión actual; límites, MIME, clave de idempotencia y redacción en telemetría. |
| Cambios de esquema trazables | PASS | No requiere migración PostgreSQL. |
| Comparabilidad | PASS | El endpoint llama al mismo puerto `ChatPattern` mediante `SendChatMessage`; se prueba contrato equivalente con los tres patrones. |
| Separación por capas | PASS | Puerto de aplicación y adaptador de infraestructura Groq; FastAPI solo valida/transfiere la solicitud. |

### Gates después del diseño

PASS: no hay dependencia Groq en `domain` ni llamada directa desde la ruta; no se modifica la persistencia; no se reduce la trazabilidad académica de los patrones, siempre que las entradas/salidas sigan ocultas para el turno de voz.

## Design Decisions

1. **Endpoint separado**: `POST /api/chat/audio` consume multipart para no cambiar `POST /api/chat` JSON ni afectar al frontend escrito.
2. **Caso de uso de aplicación**: valida metadatos y cuota, reclama la clave de idempotencia, llama al puerto de transcripción, rechaza texto vacío o respuesta sin voz (sin segmentos o todos con `no_speech_prob >= 0.6`) y texto superior a 2.000 caracteres, y luego ejecuta `SendChatMessage`.
3. **Adaptador Groq**: encapsula SDK, modelo fijo, idioma y timeout. Una función síncrona de FastAPI delega el trabajo de bloqueo al threadpool normal de FastAPI; no bloquea el event loop.
4. **Respuesta aditiva**: `AudioChatOut` contiene `transcript` y los mismos campos de `ChatOut`. `POST /api/chat` no añade campos ni cambia.
5. **Idempotencia temporal**: cada pulsación que inicia un envío lleva un UUID generado por el cliente. El registro de proceso asocia cliente + UUID a huella de audio y respuesta exitosa durante 10 minutos; una repetición idéntica devuelve la respuesta guardada, y reusar la clave con contenido distinto da 409. Los errores no se cachean.
6. **Cuota antes del coste**: limitador independiente de 5 solicitudes/minuto por cliente se consulta antes de llamar a Groq; si se rechaza, no hay petición de proveedor.
7. **UX del micrófono**: el control refleja estados grabando/procesando/listo/error, deshabilita doble envío mientras espera, limita a 120 s y comunica permiso denegado o formato no compatible. La caja de texto queda habilitada cuando voz falla.
8. **Despliegue**: aceptar archivo multipart hasta 25.000.000 bytes y cuerpo total hasta 25.100.000 bytes con control incremental en ASGI; revisar que el proxy de producción permita ese tamaño. No configurar transcripción activa por defecto.

## Project Structure

### Artifacts de esta feature

```text
specs/002-transcripcion-audio/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
└── contracts/
    └── audio-chat.openapi.yaml
```

### Backend a implementar

```text
app/
├── application/
│   ├── audio_chat.py             # Orquesta transcripción e SendChatMessage
│   ├── audio_requests.py         # Cuota e idempotencia efímera
│   └── ports.py                 # Protocolo AudioTranscriber
├── adapters/
│   ├── api/chat.py              # POST /api/chat/audio y mapeo de errores
│   └── speech/groq.py           # Implementación del puerto con SDK Groq
├── chat/contract.py             # AudioChatOut y campos multipart compartidos
├── infrastructure/
│   ├── chat_app.py               # Inyección de puerto, flags y límites
│   └── request_limits.py         # Límite incremental del cuerpo multipart
└── settings.py                  # Flag y parámetros de audio

requirements-agent.txt           # python-multipart
.env.example                     # bandera y límites documentados
tests/
├── unit/application/            # Flujo de voz, cuota, idempotencia y fallos
├── unit/adapters/               # Adaptador Groq con cliente simulado
├── integration/                 # Sesión, multipart, ruta y contratos por patrón
└── contract/                    # Igual entrada transcrita y política para 3 patrones
```

**Frontend externo**: `../TechFixAI-frontend` (React + Vite, URL indicada en `README.md`). Integración acordada mediante contrato HTTP: botón de micrófono, captura `MediaRecorder`, envío multipart, estados de interfaz, render de transcripción y respuesta. Las rutas frontend se revisaron en el workspace y sus tareas se expresan relativas a la raíz del backend.

**Structure Decision**: Mantener la arquitectura Clean existente (`domain`, `application`, `adapters`, `infrastructure`). La nueva capacidad es transversal y no se incluye en los tres grafos; todos reciben el mismo texto a través del caso de uso común.

## Complexity Tracking

Sin violaciones de la constitución ni componentes adicionales. La idempotencia temporal es necesaria para cumplir la aceptación de no crear turnos repetidos; su alcance por proceso coincide con el registro de conversaciones existente.
