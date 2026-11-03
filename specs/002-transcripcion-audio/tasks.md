---
description: "Tareas locales del backend para transcripción de audio en el chat"
---

# Tasks: Transcripción de audio para el chat — Backend

**Source of truth**: Esta carpeta contiene la spec y el contrato canónicos de la feature. Las tareas del frontend están en su propio repositorio: [frontend tasks](../../../TechFixAI-frontend/specs/002-transcripcion-audio/tasks.md).

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/audio-chat.openapi.yaml`, `quickstart.md`.

**Tests**: Las pruebas de API y contrato se escriben primero para los escenarios de audio; los patrones usan transcriptor falso y no llaman a Groq.

**Format**: `- [ ] T### [P?] [US?] acción concreta con ruta`. `[P]` indica trabajo paralelo en archivos distintos; Setup y Foundational no llevan etiqueta de historia.

## Phase 1: Setup

**Purpose**: Habilitar recepción de `multipart/form-data`.

- [X] T001 Añadir y fijar una versión de `python-multipart` compatible con FastAPI en `requirements-agent.txt`.

---

## Phase 2: Foundational

**Purpose**: Configuración y contratos comunes requeridos antes del endpoint.

### Tests primero

- [X] T002 [P] Añadir pruebas para la bandera `AUDIO_TRANSCRIPTION_ENABLED` (desactivada por defecto) y límites positivos en `tests/unit/infrastructure/test_settings.py`.
- [X] T003 [P] Añadir pruebas del límite incremental del cuerpo multipart (413 al superar 25.100.000 bytes) en `tests/unit/infrastructure/test_request_limits.py`.

### Implementación

- [X] T004 Añadir en `app/settings.py` y `.env.example` configuración de audio desactivada por defecto, timeout de 30 s, máximo de 25.000.000 bytes, duración máxima de 120 s y cuota de 5 solicitudes por minuto.
- [X] T005 Implementar el límite ASGI incremental de 25.100.000 bytes en `app/infrastructure/request_limits.py` y registrarlo en `app/infrastructure/chat_app.py`.
- [X] T006 [P] Definir el protocolo `AudioTranscriber` y resultado temporal de transcripción en `app/application/ports.py`, sin importar el SDK Groq.
- [X] T007 [P] Añadir `AudioChatOut` con `transcript` y los campos existentes de `ChatOut` en `app/chat/contract.py`; mantener `POST /api/chat` sin cambios.

**Checkpoint**: Configuración, límites de carga y contratos listos; sin cambios en PostgreSQL.

---

## Phase 3: User Story 1 — Consultar por voz (P1, MVP backend)

**Goal**: Recibir audio autenticado, transcribirlo y pasar el texto a `SendChatMessage` con el cliente, patrón y conversación correctos.

**Independent Test**: Enviar multipart con sesión válida y Groq simulado; verificar que vuelve transcripción + respuesta y que los tres patrones reciben la misma entrada mediante el caso de uso compartido.

### Tests for User Story 1

> Escribir y ejecutar primero estas pruebas; deben fallar porque el endpoint aún no existe.

- [X] T008 [P] [US1] Añadir prueba unitaria del caso de uso con transcriptor falso y `SendChatMessage` en `tests/unit/application/test_audio_chat.py`.
- [X] T009 [P] [US1] Añadir prueba de éxito y autenticación de `POST /api/chat/audio` multipart en `tests/integration/test_audio_chat_api.py`.
- [X] T010 [P] [US1] Añadir contrato que verifique la misma transcripción en los tres patrones en `tests/contract/patterns/test_audio_chat_patterns.py`.

### Implementation for User Story 1

- [X] T011 [P] [US1] Implementar `GroqAudioTranscriber` en `app/adapters/speech/groq.py` con modelo `whisper-large-v3-turbo`, idioma `es`, `verbose_json`, temperatura 0, timeout de 30 s y rechazo cuando no haya segmentos o todos tengan `no_speech_prob >= 0.6`.
- [X] T012 [P] [US1] Implementar `SendAudioChatMessage` en `app/application/audio_chat.py`; validar duración 1–120.000 ms, tipo y tamaño máximo de 25.000.000 bytes, transcripción no vacía de máximo 2.000 caracteres y delegar en `SendChatMessage`.
- [X] T013 [US1] Añadir `POST /api/chat/audio` en `app/adapters/api/chat.py` con campos multipart `audio`, `duration_ms`, `pattern`, `conversation_id`, `request_id` y respuesta definida en `specs/002-transcripcion-audio/contracts/audio-chat.openapi.yaml`.
- [X] T014 [US1] Inyectar transcriptor y caso de uso en `app/infrastructure/chat_app.py`; responder con error recuperable si `AUDIO_TRANSCRIPTION_ENABLED=false`.

**Checkpoint**: API demostrable con proveedor falso y misma política/entrada en los tres patrones.

---

## Phase 4: User Story 2 — Recuperarse de errores de audio (P2)

**Goal**: Rechazar audio inválido, silencio, límites excedidos y fallos sin crear turnos ni exponer datos; controlar costes y reintentos.

**Independent Test**: Provocar cada error con proveedor simulado; confirmar código recuperable, cero invocaciones al patrón ante entradas inválidas y máximo un turno para un mismo envío aceptado.

### Tests for User Story 2

- [X] T015 [P] [US2] Añadir pruebas de cuota 5/minuto, expiración, huella distinta y duplicados concurrentes en `tests/unit/application/test_audio_request_guards.py`.
- [X] T016 [P] [US2] Añadir pruebas del endpoint para MIME/tamaño, silencio, transcript largo, proveedor deshabilitado/timeout y ausencia de turno en `tests/integration/test_audio_chat_api.py`.
- [X] T017 [P] [US2] Añadir prueba de redacción de entradas y salidas de voz en `tests/unit/adapters/test_audio_trace_privacy.py`.

### Implementation for User Story 2

- [X] T018 [US2] Implementar `AudioRequestRegistry` en `app/application/audio_requests.py` con cuota por cliente, idempotencia y huella; conservar respuestas exitosas por 10 minutos, bloquear duplicados simultáneos y no cachear errores.
- [X] T019 [US2] Añadir errores tipados y mapeos HTTP 413/415/422/429/503/504 en `app/application/errors.py`, `app/application/audio_chat.py` y `app/adapters/api/chat.py`; aplicar la cuota antes de contactar a Groq.
- [X] T020 [US2] Impedir que una configuración de audio con LangSmith exponga inputs/outputs en `app/settings.py` y `app/adapters/llm/tracing.py`; mantener credenciales, audio y transcripción fuera de logs/trazas.

**Checkpoint**: Ningún error de proveedor o audio produce un turno incompleto; los reintentos exitosos no duplican el turno.

---

## Phase 5: User Story 3 — Consultar transcripción en turnos siguientes (P3)

**Goal**: Asegurar que la transcripción permanece dentro de la conversación seleccionada y que un turno posterior puede continuarla.

**Independent Test**: Ejecutar un turno de audio y otro escrito con el mismo cliente; comprobar mismo `conversation_id` y patrón y transcripción presente una sola vez en el contexto.

### Tests for User Story 3

- [X] T021 [P] [US3] Añadir prueba de turno de audio seguido de mensaje escrito en la misma conversación/patrón en `tests/integration/test_audio_chat_api.py`.

### Implementation for User Story 3

- [X] T022 [US3] Integrar el envío transcrito con el registro normal de conversación en `app/application/audio_chat.py`, conservando el `conversation_id` y patrón para turnos posteriores.

**Checkpoint**: Backend preserva el hilo y nunca crea una conversación secundaria solo por usar voz.

---

## Phase 6: Polish & Cross-Cutting

- [X] T023 [P] Documentar configuración y endpoint en `README.md` y `app/chat/README.md`, enlazando el contrato canónico `specs/002-transcripcion-audio/contracts/audio-chat.openapi.yaml`.
- [X] T024 Ejecutar las pruebas backend de unidad, integración y contrato indicadas en `specs/002-transcripcion-audio/quickstart.md`.

---

## Dependencies & Parallel Execution

- Setup T001 precede Phase 2.
- Phase 2 precede todas las historias.
- US1 precede US2 porque US2 endurece la ruta y el caso de uso introducidos por US1.
- US3 depende de US1; puede planificarse junto a US2, pero implementar después de que el endpoint establezca su contrato de conversación.
- Polish sigue a las historias que se entreguen.

### Parallel opportunities

- T002/T003; luego T006/T007.
- T008/T009/T010; luego T011/T012.
- T015/T016/T017; luego T018/T020 en archivos separados.
- T023 puede ejecutarse en paralelo con T024.

## MVP

Completar T001–T014 para entregar la API de voz con proveedor simulado, y validar su comportamiento en los tres patrones. La integración visual se entrega con las tareas frontend locales.
