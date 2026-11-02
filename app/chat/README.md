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

## API integrada

El punto de entrada recomendado ejecuta cuentas y chat en el mismo servidor:

```bash
.venv/Scripts/python -m uvicorn app.main:app --host localhost --port 8000
```

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
