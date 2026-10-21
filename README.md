# Sistema Multiagente de Servicio Técnico, Ventas y Soporte

TechFix.AI: plataforma para un taller de reparación de equipos. El cliente se registra, inicia sesión y conversa
con agentes LangGraph que orientan sobre fallas y preparan propuestas; los patrones Jerárquico y Orquestador
consultan repuestos y pueden guardar tickets/presupuestos.

El proyecto compara tres patrones multiagente con LangGraph, con herramientas y trazabilidad en LangSmith:
**Orquestador/Supervisor**, **Jerárquico** y **Red Descentralizada**. Comparten frontend y autenticación; la
persistencia de inventario y presupuestos está disponible en los dos primeros patrones.

## Módulos

| Módulo | Carpeta | Estado |
| --- | --- | --- |
| Landing, portal del cliente y panel del taller (React) | [`landing/`](landing/README.md) | En `main` |
| Cuentas: registro, inicio de sesión, recuperación de contraseña | [`app/accounts/`](app/accounts/README.md) | En `main` |
| API unificada de cuentas y chat | [`app/combined.py`](app/combined.py) | Integrada |
| Sesión reutilizable y contrato común del chat (`POST /api/chat`) | [`app/chat/`](app/chat/README.md), [`app/main.py`](app/main.py) | Integrados |
| Agente de ventas y trazas locales | `app/agents/sales.py`, `app/tracing.py` | En `main` |
| Patrón de Red Descentralizada | [`app/agents/decentralized/`](app/agents/decentralized/) | Integrado; herramientas aún simuladas |
| Patrón Jerárquico | [`app/agents/jerarquico/`](app/agents/jerarquico/) | Integrado; consulta y persistencia PostgreSQL |
| Patrón Orquestador/Supervisor | [`app/agents/orquestador/`](app/agents/orquestador/) | Integrado; consulta y persistencia PostgreSQL |
| Correo transaccional (SMTP) | `app/email/` | En `main` |

## Integración de patrones

El chat React permite seleccionar Jerárquico, Orquestador o Descentralizado antes
del primer mensaje. Cada conversación conserva el patrón elegido; para cambiarlo
hay que iniciar otra. El backend aplica `SessionGuard` a `GET /api/chat/patterns` y
`POST /api/chat`, identifica al cliente mediante la cookie autenticada y pasa el
UUID de conversación como `thread_id` de LangGraph.

Los patrones Jerárquico y Orquestador usan sus motores de negocio existentes para
preparar y guardar tickets/presupuestos. La Red Descentralizada queda marcada en
la interfaz como experimental: sus herramientas todavía son simuladas y no consulta
inventario ni persiste tickets/presupuestos. No se declara paridad funcional entre
los tres motores.

LangSmith recibe la etiqueta del patrón y el UUID de conversación; el
código configura el cliente con entradas y salidas ocultas y redacta el texto de
errores. No se incluyen correo ni texto del usuario en los metadatos explícitos.
La integración con servicios reales de Groq, PostgreSQL y LangSmith requiere
configurar el entorno local.

Ver [`spec/06-integracion-patrones.md`](spec/06-integracion-patrones.md) y
[`docs/06-integracion-patrones.md`](docs/06-integracion-patrones.md) para alcance,
decisiones, validación y limitaciones del bloque.

## Arquitectura

```text
 Navegador (React + Vite, landing/)
   │ cuentas: /auth/*       │ chat: /api/chat
   ▼                        ▼
 API unificada (app/combined.py): cuentas + patrones LangGraph
   │ cookie HttpOnly compartida; SessionGuard valida la sesión
   ▼
 PostgreSQL: users · recovery_tokens · tickets · quotes · spare_parts …   ◀── grafo LangGraph del patrón
                                                                             │ herramientas · LangSmith
```

- La identidad del cliente sale siempre de la cookie firmada; el chat nunca pide el correo.
- Cada patrón expone el mismo `POST /api/chat`, así el frontend funciona con cualquiera de ellos. La guía para
  conectar un patrón está en [`app/chat/README.md`](app/chat/README.md).

## Estructura

```text
app/
├── accounts/        API de cuentas (FastAPI): /registro, /login, /logout, /me, /recuperar, /restablecer
├── combined.py      Punto de entrada unificado: monta cuentas en /auth junto al chat
├── chat/            Contrato de /api/chat, patrón de referencia y modelo de tickets
├── agents/
│   ├── jerarquico/     Supervisor, soporte, ventas, almacén, RAG y persistencia
│   ├── orquestador/    Supervisor, agentes, herramientas y recuperación
│   ├── decentralized/ Red descentralizada con agentes/herramientas simuladas
│   └── sales.py        Agente previo de ventas de demostración (Decimal)
├── database/        Conexión SQLAlchemy a PostgreSQL
├── email/           Servicio SMTP y plantillas
├── main.py          API autenticada del chat y selector de patrones LangGraph
└── tracing.py       Trazas locales JSONL sin contenido de los mensajes
landing/             Frontend React 18 + Vite
postman/             Colección de la API de cuentas
tests/               Pruebas automáticas (pytest)
```

## Requisitos

- Python 3.12
- Node.js 18 o superior
- PostgreSQL 16 con las tablas del script del equipo (`creacion_tablas_sin_inserciones.sql`)
- Claves de Groq y LangSmith para los patrones con LLM

## Configuración

Copiar `.env.example` a `.env` y completar:

| Variable | Uso |
| --- | --- |
| `DATABASE_URL` | `postgresql+pg8000://USUARIO:CLAVE@localhost:5432/techfix` |
| `AUTH_SECRET` | Secreto para firmar la cookie; el mismo en la API de cuentas y en la del patrón |
| `AUTH_SECURE_COOKIE` | `false` solo en `localhost` sin HTTPS |
| `FRONTEND_ORIGINS`, `FRONTEND_URL` | Origen del frontend (`http://localhost:5173`) |
| `MAIL_MODE` | `outbox` guarda los correos en `OUTBOX_DIR`; `smtp` usa las variables `SMTP_*` |
| `GROQ_API_KEY` | Modelo de los agentes de los patrones |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT` | Trazabilidad en LangSmith |
| `LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS` | Ocultamiento de contenido en las trazas |

La instalación raíz incluye las dependencias de API, agentes y RAG mediante
`requirements-agent.txt`. Para crear o actualizar el índice vectorial local una
vez instaladas las dependencias, ejecuta:

```powershell
.\.venv\Scripts\python.exe -m app.rag.ingest
```

La ingesta descarga el modelo FastEmbed la primera vez y guarda el índice en
`data/chroma/`, que está excluido de Git. Debe repetirse cuando cambie el
contenido de `data/knowledge/`.

El frontend usa `landing/.env` (ver `landing/.env.example`): `VITE_API_URL` apunta a
`/auth` y `VITE_CHAT_URL` al mismo origen del chat. Los valores locales por defecto
son `http://localhost:8000/auth` y `http://localhost:8000`; Vite los carga al
iniciar, así que reinicia el servidor frontend después de modificarlos.

## Puesta en marcha

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python -m uvicorn app.combined:create_app --factory --host localhost --port 8000
```

```bash
npm --prefix landing install
```

```bash
npm --prefix landing run dev
```

Abrir http://localhost:5173. El proceso unificado expone las rutas de cuentas
en `/auth/*` y el chat en `/api/chat`; ambos clientes usan el mismo host y puerto.
Para los endpoints independientes, ver la documentación de sus módulos.

## Pruebas

```bash
npm --prefix landing test
```

```bash
.venv/Scripts/python -m pytest tests --ignore=tests/test_database.py --ignore=tests/test_email.py --ignore=tests/test_e2e_decentralized.py -q
```

- `tests/test_database.py` y `tests/test_email.py` son scripts manuales que acceden a PostgreSQL y SMTP reales;
  no se deben incluir en la suite aislada.
- `tests/test_e2e_decentralized.py` llama a Groq real; se excluye de la suite aislada para evitar llamadas externas.
- API de cuentas con Postman o Newman: `npx newman run postman/techfix-auth.postman_collection.json`.

## Seguridad

- Contraseñas con bcrypt; nunca se guardan, devuelven ni registran en texto plano.
- Sesión en cookie `HttpOnly` y `SameSite=Lax`, firmada; restablecer la contraseña cierra las sesiones abiertas.
- Importes con `Decimal`; los precios salen del catálogo de prueba.
- Las trazas y los registros no guardan mensajes, credenciales ni textos de excepciones.

## Contribuir

- Una rama por tarea y Pull Request hacia `main`; no subir directamente a `main`.
- Mensajes con *conventional commits*: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.
- Antes de abrir el PR: traer `main` a la rama, resolver conflictos y pasar las pruebas.

## Limitaciones actuales

- Las conversaciones y el bloqueo entre patrones residen en memoria del proceso; ejecutar una sola instancia.
- La Red Descentralizada usa herramientas simuladas y no guarda tickets ni presupuestos en PostgreSQL.
- Tickets, inventario y "Mis Tickets" del frontend usan datos de demostración.
- `npm audit --omit=dev` reporta dos vulnerabilidades moderadas en React Router; el arreglo sugerido por npm
  salta a la versión 7 y requiere evaluar cambios incompatibles antes de aplicarlo.
