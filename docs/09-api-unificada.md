# Evidencia 09 — API unificada de cuentas y chat

## Cambio

Históricamente `app.combined:create_app` montaba la API de cuentas en `/auth`
dentro de la aplicación del chat, preservando `/api/chat` y
`/api/chat/patterns`. En 2026-10-27 la composición se movió al punto estándar
`app.main:app` y se retiró el módulo combinado separado. La misma configuración
y fábrica SQLAlchemy se comparte con `SessionGuard`.

Las URLs configuradas para el frontend local son:

```dotenv
VITE_API_URL=http://localhost:8000/auth
VITE_CHAT_URL=http://localhost:8000
```

Se actualizaron las instrucciones de ejecución y configuración del frontend.
No se añadieron manifiestos ni archivos de despliegue.

## Validación

- Validación histórica del punto de entrada combinado: `pytest tests/test_combined_api.py tests/test_pattern_api.py tests/test_accounts_api.py -q`, 29 aprobadas. La consolidación posterior en `app.main:app` todavía no se ha validado con suite automatizada.
- `npm --prefix landing test -- tests/register.test.jsx`: 11 aprobadas.
- `npm --prefix landing run build`: aprobado.
- Pylance syntax check de la implementación histórica y `tests/test_combined_api.py`: sin errores.
- La primera ejecución completa de Vitest tuvo un timeout de 5 segundos en una prueba de registro bajo carga concurrente; la suite dirigida de ese archivo pasó al ejecutarse aislada.

La prueba de integración confirma que una cookie emitida por `/auth/login`
autoriza `GET /api/chat/patterns` en la misma aplicación. La verificación usa
SQLite en memoria y no requiere PostgreSQL, Groq ni LangSmith.
