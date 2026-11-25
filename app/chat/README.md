# Chat del portal — sesión del login y contrato común

El chat del portal (`/portal/asistente` en [TechFixAI-frontend](https://github.com/SebasBazauri/TechFixAI-frontend)) habla con el patrón LangGraph del equipo mediante
`POST /api/chat`. El cliente se identifica con la cookie de sesión de la API de cuentas, nunca con un correo
escrito en el chat.

| Archivo | Uso |
| --- | --- |
| `app/accounts/session.py` | `SessionGuard`: dependencias `require_customer` y `require_user` para FastAPI |
| `app/chat/contract.py` | Modelos del contrato: `ChatIn`, `ChatOut`, `QuoteOut`, `TicketOut` |
| `app/chat/models.py` | Mapeo de la tabla `tickets` del script de BD |
| `app/main.py` | Punto único de entrada; monta cuentas y chat con la raíz de composición |
| `app/adapters/patterns/` | Un adaptador por patrón LangGraph (puerto `ChatPattern`); para sumar un patrón se agrega su adaptador al registro |
| `app/chat/reference.py` | API de referencia independiente para probar el contrato |

| `app/application/audio_chat.py` | Transcribe y delega en el mismo caso de uso del chat escrito |
| `app/adapters/speech/groq.py` | Adaptador Groq Whisper con errores seguros |
| `app/infrastructure/request_limits.py` | Limite incremental del cuerpo multipart |

## Contrato `POST /api/chat`

Petición (cookie `techfix_session` obligatoria):

```json
{ "conversation_id": null, "message": "Mi laptop HP no detecta el disco", "action": null, "pattern": "hierarchical" }
```

`pattern` puede ser `hierarchical`, `orchestrator` o `decentralized`; si se omite,
el backend usa `hierarchical`. El patrón no se puede cambiar en una conversación
existente. `action` puede ser `"accept_quote"` o `"reject_quote"` (botones de la
tarjeta de propuesta). Campos como `email` o `customer_id` en el cuerpo se ignoran.
`GET /api/chat/patterns` lista los patrones y requiere la misma sesión.

Respuesta `200`:

```json
{
  "conversation_id": "…",
  "reply": "Texto del agente",
  "quote": { "status": "proposed", "lines": [{ "label": "SSD de 480 GB", "amount": "180.00" }], "total": "260.00", "currency": "PEN" },
  "ticket": { "code": "TCK-4F2A1C", "status": "QUOTED" }
}
```

| Código | Cuándo |
| --- | --- |
| `401` `session_required` | Sin sesión, cookie inválida o vencida, cuenta inactiva o contraseña cambiada |
| `403` `customer_only` | Usuario de rol técnico o administrador |
| `404` | Conversación inexistente o de otro cliente |
| `409` | Acción sin presupuesto pendiente |
| `422` | Cuerpo inválido (no se repite el mensaje) |
| `429` | Más de 20 mensajes por minuto |
| `502` | Error procesando con el proveedor LLM o el patrón |
| `503` | Base de datos o almacenamiento no disponibles |

## Contrato de audio `POST /api/chat/audio`

La ruta usa la misma sesion autenticada y acepta `audio`, `duration_ms`, `pattern`,
`request_id` y opcionalmente `conversation_id` como `multipart/form-data`. El resultado
agrega `transcript` a los campos habituales de `ChatOut`. Solo admite audio hasta 25 MB
y 120 segundos; una cuota de cinco envios por minuto y la idempotencia por cliente
protegen las llamadas a Groq. El arranque exige ocultar inputs y outputs de LangSmith
si el tracing esta activo.

`AUDIO_TRANSCRIPTION_ENABLED` vale `false` por defecto. Para activar voz, configura
esa bandera y `GROQ_API_KEY`; revisa timeout y limites en `.env.example`. El archivo
se procesa temporalmente y se cierra al terminar. El endpoint no cambia `POST /api/chat`.

El contrato canonico es
[`specs/002-transcripcion-audio/contracts/audio-chat.openapi.yaml`](../../specs/002-transcripcion-audio/contracts/audio-chat.openapi.yaml).
La tarea frontend se implementa y valida en el repositorio hermano.

## «Mis Tickets» del cliente

`GET /api/customer/tickets` toma el perfil comercial de la sesión autenticada y devuelve solo sus tickets. Cada ticket incluye `diagnosis_type`, `hardware_diagnosis` y `software_diagnosis`, además de sus cotizaciones y líneas. Los campos de diagnóstico corresponden a la evaluación persistida por los especialistas; para tickets aún sin evaluación, el tipo es `NONE` y los textos son `null`. La propiedad se valida en la consulta del repositorio mediante `commercial_customer_id`; el request no puede elegir otro cliente.

El contrato vigente está en [`specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml`](../../specs/007-gestion-clientes-comerciales/contracts/customer-commerce.openapi.yaml).

## API integrada

El punto de entrada recomendado ejecuta cuentas y chat en el mismo servidor:

```bash
.venv/Scripts/python -m uvicorn app.main:app --host localhost --port 8000
```

## API administrativa de tickets

- `GET /api/admin/customers?email=...`: busca una cuenta cliente activa para asociarla al alta manual.
- `GET /api/admin/tickets`: lista tickets; admite filtros `status`, `request_type`, `search`, `limit` y `offset`.
- `GET /api/admin/tickets/{id}`: obtiene detalle.
- `POST /api/admin/tickets`: crea un ticket asociado a `customer_email`.
- `PATCH /api/admin/tickets/{id}`: actualiza solo los campos enviados.
- `DELETE /api/admin/tickets/{id}`: elimina físicamente el ticket y las relaciones con borrado en cascada.

Todas las rutas requieren sesión `techfix_session` de usuario activo con rol `ADMIN`; rol `TECHNICIAN` no concede acceso. La guía paso a paso para Postman está en `contexto/CRUD-tickets-admin-postman.md`.

Las rutas de cuentas quedan bajo `/auth/*`; el chat conserva `/api/chat` y
`/api/chat/patterns`. Este es el punto de entrada recomendado para el backend
completo; para pruebas aisladas se inyectan fábricas y dependencias a `create_app`.

El portal comparte el contrato, pero los motores no tienen la misma paridad de
persistencia: Jerárquico y Orquestador conectan sus herramientas de negocio a
PostgreSQL; Red Descentralizada sigue siendo un prototipo con herramientas
simuladas, sin lectura de inventario ni persistencia de tickets/presupuestos.
El selector se bloquea al iniciar una conversación; iniciar otra crea un nuevo
`thread_id` y permite elegir otro patrón.

LangSmith es controlado por `LANGSMITH_TRACING`, `LANGSMITH_API_KEY` y
`LANGSMITH_PROJECT`; inputs y outputs se ocultan mediante
`LANGSMITH_HIDE_INPUTS`/`LANGSMITH_HIDE_OUTPUTS`. Los metadatos explícitos
contienen el patrón y UUID de conversación, no ID de cliente, correo ni mensaje.

## API de referencia

```bash
.venv/Scripts/python -m uvicorn app.chat.reference:create_reference_app --factory --host localhost --port 8001
```

La API de referencia es independiente y no es el punto de entrada usado por el
selector de patrones.

En el frontend, definir `VITE_API_URL=http://localhost:8000/auth` y
`VITE_CHAT_URL=http://localhost:8000` en el `.env` del frontend.

## Pruebas

```bash
.venv/Scripts/python -m pytest tests/test_session_guard.py tests/test_chat_reference.py -q
```
