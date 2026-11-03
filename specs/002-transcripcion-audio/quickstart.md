# Quickstart de validación: Transcripción de audio para el chat

Este documento guía la validación después de implementar la feature. Las pruebas de API usan transcriptor simulado; no llaman a Groq ni requieren una clave para comprobar el flujo de aplicación.

## Prerrequisitos

- Python 3.12 y entorno virtual con las dependencias de `requirements-agent.txt`.
- PostgreSQL configurado igual que para el chat existente, o fixtures SQLite usados por las pruebas.
- Una sesión de cliente válida para la prueba manual.
- Para UI: checkout separado de `TechFixAI-frontend`, Node.js 18+ y navegador en HTTPS o localhost con soporte de micrófono.
- Para probar Groq real: `GROQ_API_KEY` configurada en el backend y `AUDIO_TRANSCRIPTION_ENABLED=true`; nunca compartir ni registrar el valor.

## Instalar e iniciar el backend

```powershell
python -m pip install -r requirements-agent.txt
python -m uvicorn app.main:app --host localhost --port 8000 --reload
```

La transcripción debe permanecer desactivada si no se configuró la clave. Los mensajes de texto deben continuar respondiéndose en ese modo.

## Pruebas automáticas

```powershell
python -m pytest -q tests/unit/application/test_audio_chat.py tests/unit/adapters/test_groq_transcriber.py tests/integration/test_audio_chat_api.py tests/contract/patterns/test_audio_chat_patterns.py
```

Resultados que se deben verificar:

1. Un audio válido se transcribe una sola vez y el texto resultante se envía a cada patrón por el contrato común de `SendChatMessage`.
2. Una sesión no autenticada recibe `401`; el identificador del cliente nunca proviene del multipart.
3. Audio vacío, tipo no admitido, exceso de bytes o duración reportada superior al límite falla antes de invocar Groq o el patrón.
4. Silencio (sin segmentos o todos con `no_speech_prob >= 0.6`), texto vacío, transcripción de más de 2.000 caracteres, timeout, cuota agotada y proveedor indisponible no inician un turno multiagente.
5. Un reintento con el mismo cliente, `request_id` y audio devuelve la respuesta exitosa previa sin otra transcripción ni turno; la misma clave con otra huella devuelve `409`.
6. LangSmith no recibe entradas/salidas visibles para turnos de audio; logs y errores no contienen texto, archivo, nombre de archivo ni clave.
7. Con audio deshabilitado, el endpoint devuelve una explicación recuperable y `POST /api/chat` escrito sigue funcionando.

## Validación del contrato multipart

Con una cookie de sesión ya iniciada y un archivo de audio compatible (máximo 25 MB), la forma equivalente en `curl` es:

```bash
curl -b cookies.txt \
  -F "audio=@consulta.webm;type=audio/webm" \
  -F "duration_ms=8400" \
  -F "pattern=hierarchical" \
  -F "request_id=6f3e1f2d-32a4-4a5b-8a7a-2dd01108d421" \
  http://localhost:8000/api/chat/audio
```

Respuesta esperada: HTTP 200 con `transcript`, `conversation_id`, `reply`, `pattern` y, cuando apliquen, `quote` o `ticket`. Usa un UUID nuevo para cada intento que deba considerarse distinto.

## Validación manual de la UI

1. En el repositorio frontend, configurar `VITE_CHAT_URL=http://localhost:8000` y arrancar Vite con `npm install` y `npm run dev`.
2. Iniciar sesión como cliente y seleccionar cualquiera de los tres patrones antes del primer turno.
3. Pulsar el botón de micrófono: debe indicar que está grabando y no enviar todavía.
4. Dictar una pregunta y volver a pulsar: debe detener, mostrar estado procesando, enviar la grabación una vez y renderizar transcripción + respuesta en la conversación seleccionada.
5. Repetir con permiso denegado, grabación vacía/silenciosa, límite de 120 s, audio mayor a 25 MB en prueba de API, proveedor deshabilitado y conexión fallida. En cada error debe permitirse continuar escribiendo.
6. En la pestaña Network confirmar `multipart/form-data` con boundary automático, cookie de sesión y respuesta sin datos de audio; nunca fijar manualmente el header `Content-Type` del multipart.

El frontend está en el repositorio hermano `../TechFixAI-frontend`; los comandos manuales se ejecutan desde su propia raíz.
