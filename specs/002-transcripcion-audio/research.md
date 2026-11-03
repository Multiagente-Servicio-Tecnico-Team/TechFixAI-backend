# Research: Transcripción de audio para el chat

## Decisiones

### Proveedor y modelo

- **Decisión**: Usar el endpoint de transcripciones de Groq con `whisper-large-v3-turbo`, idioma `es` y temperatura `0`. Solicitar `verbose_json`; usar el texto de transcripción y los metadatos `no_speech_prob` únicamente para descartar silencio, sin guardar los segmentos.
- **Racional**: Es el proveedor/modelo pedido. La documentación oficial lista el modelo como multilingüe y el idioma ISO-639-1 opcional puede mejorar precisión y latencia. `verbose_json` expone la probabilidad de ausencia de voz por segmento, necesaria para no enrutar silencio que el modelo haya interpretado como palabras. Rechazar como audio sin voz si no hay segmentos o todos los segmentos tienen `no_speech_prob >= 0.6`; confirmar ese umbral con clips de aceptación. El modo transcripción conserva el idioma hablado; no se debe usar el endpoint de traducción al inglés.
- **Alternativas consideradas**: Transcripción en el navegador, otro proveedor, traducción de voz. Se descartan para este alcance porque el backend debe realizar la transcripción y el texto debe llegar a los patrones sin cambiar idioma.
- **Fuente**: [Groq Speech to Text](https://console.groq.com/docs/speech-to-text), [Groq API Reference: Audio Transcriptions](https://console.groq.com/docs/api-reference).

### Límites de audio

- **Decisión**: Limitar cada grabación a 120 segundos y cada carga a 25.000.000 bytes. El frontend detiene la captura al alcanzar la duración; el backend limita estrictamente el tamaño de la carga antes de llamar a Groq. Publicar ambos límites en la interfaz.
- **Racional**: Las páginas oficiales de Groq no son consistentes sobre el tamaño máximo: la guía de Speech to Text indica 25 MB en Free y 100 MB en Developer, mientras que la página del modelo indica 100 MB. El tope propio de 25 MB queda por debajo del más conservador y evita depender del plan de la cuenta. El máximo de 120 s es un límite de producto para una consulta conversacional breve, no una restricción del modelo.
- **Alternativas consideradas**: Usar 100 MB, o aceptar cualquier duración y delegar el rechazo al proveedor. Se descartan para reducir transferencia, memoria, coste y variación entre cuentas.
- **Formatos**: Validar el tipo de medio contra `flac`, `mp3`, `mp4`, `mpeg`, `mpga`, `m4a`, `ogg`, `wav` y `webm`. El navegador debe seleccionar entre los formatos de grabación que soporte y que acepte Groq; no se convierte el audio en el servidor.
- **Coste mínimo**: La guía indica que el mínimo facturado es de 10 segundos aunque el audio sea más corto. No enviar audio vacío; las grabaciones cortas siguen sujetas al mínimo del proveedor.
- **Fuente**: [Groq Speech to Text: Audio File Limitations](https://console.groq.com/docs/speech-to-text), [Groq Whisper Large V3 Turbo](https://console.groq.com/docs/model/whisper-large-v3-turbo).

### Separación por capas

- **Decisión**: Añadir un puerto de aplicación para transcripción, un adaptador Groq independiente y un caso de uso que transcribe y luego invoca el `SendChatMessage` existente. La API y los patrones no importan el SDK Groq directamente.
- **Racional**: La constitución exige que el dominio/aplicación no se acoplen a Groq. El puerto deja sustituir el proveedor en pruebas, y el caso de uso conserva las reglas compartidas, la conversación y la selección de patrón.
- **Alternativas consideradas**: Llamar a Groq desde la ruta FastAPI o crear lógica de audio dentro de cada patrón. Se descartan por acoplamiento y por duplicar comportamiento entre patrones.

### API y experiencia de voz

- **Decisión**: Exponer `POST /api/chat/audio` como `multipart/form-data` con audio, patrón, identificador opcional de conversación e identificador de solicitud. Requiere la misma cookie de sesión que `POST /api/chat`. La respuesta añade `transcript` y conserva los campos existentes de respuesta.
- **Racional**: El audio no cabe en el contrato JSON actual de `ChatIn`; una ruta aparte conserva la compatibilidad del flujo de texto. El frontend usa MediaRecorder: primer toque inicia, segundo detiene y envía; no hay pantalla de confirmación.
- **Alternativas consideradas**: Codificar audio en Base64 dentro de JSON, o alterar el contrato de `POST /api/chat`. Se descartan por inflar la carga y por mezclar formatos de entrada incompatibles.
- **Idempotencia**: El frontend genera un UUID por intento. El backend conserva temporalmente el resultado de intentos exitosos por cliente y clave, y devuelve el resultado previo si el navegador reintenta tras perder la respuesta. Reutilizar una clave con una conversación/patrón distintos produce `409`.

### Límites de uso y fallos

- **Decisión**: Aplicar un límite separado de 5 solicitudes de audio por minuto por cliente autenticado antes de llamar al proveedor. No reintentar automáticamente fallos del proveedor; propagar una respuesta recuperable y permitir al cliente volver a grabar.
- **Racional**: Cada llamada puede generar consumo del servicio; validar el límite después de transcribir no evita el coste. Los límites exactos de Groq dependen de la organización y pueden cambiar; el límite de la aplicación es independiente.
- **Alternativas consideradas**: Reutilizar únicamente el límite de 20 mensajes/minuto, que se evalúa luego en `SendChatMessage`, o reintentar automáticamente. Se descartan porque la solicitud podría haber generado un coste antes de rechazarse o duplicar una llamada.
- **Fuente**: [Groq Rate Limits](https://console.groq.com/docs/rate-limits).

### Privacidad, trazabilidad y almacenamiento

- **Decisión**: No escribir audio en almacenamiento persistente. Cerrar el archivo temporal de carga después del uso, no registrar contenido, y mantener entradas/salidas ocultas en LangSmith para la ruta de audio. Emitir solo métricas estructuradas sin transcript, nombre de archivo ni credenciales.
- **Racional**: Satisface la política de privacidad de la constitución y los FR-010/FR-011. Se reutiliza el historial normal de conversación (en memoria en el backend actual), sin esquema SQL nuevo.
- **Alternativas consideradas**: Guardar audio o transcripción en una tabla nueva, enviar el audio como atributo de traza. Se descartan porque no son necesarios para el flujo solicitado y aumentarían el riesgo de exposición.

### Repositorios

- **Decisión**: Mantener backend y frontend en sus repositorios separados. El frontend `../TechFixAI-frontend` está disponible como carpeta hermana del workspace y sus tareas pueden indicar sus rutas revisadas.
- **Racional**: Conserva la separación actual entre equipos y deja una interfaz HTTP verificable para coordinar ambos repositorios.

## Incertidumbres cerradas

- No se cambia el esquema de PostgreSQL.
- La indisponibilidad de Groq no activa otro modelo ni una respuesta automática.
- No se hace transcripción en vivo: la petición comienza al detener la grabación.
- El proveedor usa el mismo `GROQ_API_KEY` ya configurado por los modelos de chat. Se añade una bandera `AUDIO_TRANSCRIPTION_ENABLED` desactivada por defecto para habilitarlo de forma explícita.
- La aplicación no dependerá de los rate limits publicados de una cuenta Groq; devolverá `429` recuperable cuando agote su cuota local y mapeará el límite del proveedor a un error temporal.
