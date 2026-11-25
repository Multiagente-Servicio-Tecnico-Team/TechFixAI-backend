# Feature Specification: Transcripción de audio para el chat

**Feature Branch**: `002-transcripcion-audio`

**Created**: 2026-11-02

**Status**: Draft

**Input**: User description: "Agregar speech-to-text con Groq Whisper large v3 turbo para que el backend procese el audio enviado desde el frontend y el texto transcrito pueda ser usado por el sistema multiagente."

## Clarifications

### Session 2026-11-02

- Q: ¿Cómo debe funcionar la interacción de voz en el chat? → A: Un botón de micrófono inicia la grabación; al pulsarlo de nuevo, se detiene y el audio se procesa y envía al backend para transcribirlo y usar el texto como entrada del multiagente. El chat escrito continúa disponible como alternativa.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Consultar por voz (Priority: P1)

Un cliente autenticado pulsa el botón de micrófono para empezar a dictar y vuelve a pulsarlo cuando termina. El portal detiene la grabación y la envía al backend, que obtiene la transcripción, la muestra en la conversación y la procesa como mensaje del cliente con el patrón multiagente activo. El cliente recibe la orientación habitual. También puede enviar mensajes escritos como siempre.

**Why this priority**: Permite pedir soporte o información sin tener que escribir, que es el valor principal solicitado.

**Independent Test**: Con una sesión autenticada, pulsar el micrófono, dictar una consulta y volver a pulsarlo. Verificar que aparece la transcripción como mensaje del cliente y que la respuesta corresponde a esa consulta.

**Acceptance Scenarios**:

1. **Given** un cliente autenticado, **When** pulsa el micrófono para grabar y vuelve a pulsarlo para terminar, **Then** el portal envía el audio al backend, muestra la transcripción como mensaje del cliente y procesa ese texto con el patrón seleccionado para la conversación.
2. **Given** una conversación ya iniciada con uno de los tres patrones, **When** el cliente envía una consulta por audio, **Then** se conserva la misma conversación, identidad y patrón, y recibe la respuesta con el formato habitual del chat.
3. **Given** que el cliente continúa usando mensajes de texto, **When** envía texto por el flujo actual, **Then** el mensaje se procesa igual que antes y no requiere audio.

---

### User Story 2 - Recuperarse de un audio que no se puede transcribir (Priority: P2)

El cliente recibe una explicación útil cuando el audio no es compatible, está vacío, no contiene voz reconocible o el servicio de transcripción no está disponible. Puede corregirlo o continuar escribiendo.

**Why this priority**: El cliente debe poder recuperarse sin perder la conversación ni recibir una respuesta inventada como si el audio se hubiera entendido.

**Independent Test**: Enviar audios vacíos, inválidos, sin voz o provocar una indisponibilidad del servicio y comprobar el mensaje de error y que no se invoque el sistema multiagente con contenido no transcrito.

**Acceptance Scenarios**:

1. **Given** una grabación vacía, ilegible, de formato no admitido o que excede los límites informados, **When** el cliente detiene la grabación, **Then** recibe una indicación para intentarlo de nuevo y la conversación permanece disponible.
2. **Given** audio sin voz inteligible, **When** termina el procesamiento, **Then** se informa que no se obtuvo una transcripción y no se envía un mensaje vacío al sistema multiagente.
3. **Given** que el servicio de transcripción falla, tarda más que el límite de espera o rechaza la solicitud, **When** el backend recibe el fallo, **Then** muestra un error recuperable, conserva el acceso al chat y no presenta una respuesta multiagente basada en una transcripción inexistente.
4. **Given** que el cliente no concede permiso de micrófono o el servicio de audio está deshabilitado, **When** intenta usar voz, **Then** recibe una explicación y puede seguir usando el chat escrito.
5. **Given** que el cliente reintenta un envío fallido, **When** el audio vuelve a procesarse, **Then** un único envío aceptado genera como máximo un turno en la conversación.

---

### User Story 3 - Revisar la transcripción (Priority: P3)

El cliente puede leer el texto reconocido en el historial para confirmar qué entendió el sistema y usarlo como referencia en los siguientes turnos.

**Why this priority**: La visibilidad de la transcripción ayuda a detectar errores de reconocimiento y da contexto a la respuesta recibida.

**Independent Test**: Enviar un audio válido y verificar que el texto asociado al turno del cliente se muestra en la conversación junto con la respuesta.

**Acceptance Scenarios**:

1. **Given** que se transcribió y procesó un audio correctamente, **When** se muestra el turno, **Then** la conversación identifica el texto como mensaje del cliente y presenta la respuesta asociada.
2. **Given** una transcripción con palabras o datos que el reconocimiento no pudo determinar, **When** se muestra el turno, **Then** el sistema no completa ni corrige esos datos mediante contenido inventado.
3. **Given** una solicitud de audio de un cliente autenticado, **When** el backend la asocia a una conversación, **Then** usa la identidad de la sesión y no una identidad indicada en el contenido enviado.

---

### Edge Cases

- Audio con silencio, ruido, voz superpuesta o duración sin voz reconocible: se informa que no se pudo obtener una transcripción y no se enruta un turno vacío.
- Grabación ilegible, formato no admitido, tamaño o duración superior al límite del producto: se rechaza antes de iniciar el turno multiagente y se explica cómo recuperarse.
- Expiración de sesión o cliente no autenticado: se aplican las mismas reglas de acceso del chat; el audio no se procesa para una identidad no verificada.
- Límite de uso o indisponibilidad temporal del proveedor: se muestra un error recuperable y no se cambia de patrón ni se genera una respuesta basada en texto parcial no confirmado.
- Audio en un idioma distinto del español: se conserva el idioma reconocido cuando el servicio lo soporte; el sistema no debe afirmar que entiende correctamente un idioma no reconocido.
- Reintento tras un fallo: no debe crear mensajes de conversación duplicados ni invocar varias veces el turno por un solo envío del cliente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El portal debe ofrecer un botón de micrófono que inicia la grabación de voz cuando se pulsa por primera vez y la detiene cuando se pulsa de nuevo.
- **FR-002**: Al detener la grabación, el portal debe enviar el audio al backend para transcribirlo y devolver un resultado legible para el cliente antes o junto con el resultado del chat.
- **FR-003**: Cuando exista una transcripción no vacía, el sistema debe tratarla como el mensaje del cliente dentro del flujo de conversación existente, respetando su identidad autenticada, conversación activa y patrón seleccionado.
- **FR-004**: Los tres patrones multiagente deben recibir el mismo texto normalizado para una entrada equivalente; el uso de audio no debe alterar las reglas de negocio compartidas ni el contrato de respuesta del chat.
- **FR-005**: El flujo actual de mensajes escritos debe seguir funcionando sin cambios perceptibles para el cliente.
- **FR-006**: El sistema debe validar que la grabación esté presente, sea legible, dure como máximo 120 segundos y no exceda 25 MB (25.000.000 bytes) antes de transcribirla; debe aceptar solo los formatos admitidos por el proveedor e informar los límites al cliente.
- **FR-007**: El sistema debe informar de forma clara y recuperable los casos de audio inválido, silencio o voz no reconocida, límites excedidos, tiempo de espera, límite de uso o indisponibilidad del servicio.
- **FR-008**: Si no se obtiene una transcripción válida, el sistema no debe enviar un turno vacío o parcial al sistema multiagente ni guardar una respuesta como si la consulta se hubiera entendido.
- **FR-009**: El sistema debe mostrar la transcripción junto al turno del cliente para que pueda entender qué texto se procesó.
- **FR-010**: El audio original debe descartarse después de la transcripción y no debe persistirse como parte del historial. El texto transcrito queda sujeto a las reglas existentes de la conversación.
- **FR-011**: El sistema no debe incluir el contenido del audio, credenciales del proveedor ni texto completo de la conversación en registros técnicos o trazas de evaluación.
- **FR-012**: La identidad del cliente debe obtenerse de la sesión validada, nunca de campos declarados dentro de la solicitud de audio.
- **FR-013**: El uso del servicio de transcripción debe poder deshabilitarse mediante configuración; cuando esté deshabilitado, los mensajes de texto deben seguir disponibles y el cliente debe recibir una explicación al intentar usar audio.
- **FR-014**: La transcripción debe cumplir el límite actual de 2.000 caracteres del chat; si lo excede, el sistema debe pedir al cliente que acorte su consulta y no debe truncarla silenciosamente ni enviarla al multiagente.

### Key Entities *(include if feature involves data)*

- **Audio del cliente**: Contenido temporal enviado para convertir voz en texto; no forma parte de los datos persistidos de la conversación.
- **Transcripción**: Texto reconocido a partir del audio; se asocia al turno del cliente y se procesa con las mismas reglas que un mensaje escrito.
- **Turno de chat**: Interacción existente entre cliente y asistente, asociada a identidad, conversación y patrón multiagente.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En pruebas de aceptación con audios claros en español dentro de los límites publicados, al menos 95% producen una transcripción legible o un error recuperable, sin dejar la solicitud indefinidamente pendiente.
- **SC-002**: El 100% de los audios rechazados o no transcritos se detienen antes de iniciar un turno multiagente.
- **SC-003**: Para una misma consulta transcrita, el 100% de los patrones conservan la identidad autenticada, la conversación y las políticas compartidas del mensaje de texto equivalente.
- **SC-004**: El 100% de los mensajes de texto enviados por el flujo previo siguen pudiéndose procesar sin habilitar permisos de micrófono ni configurar el proveedor de transcripción.
- **SC-005**: En las verificaciones de privacidad, no aparece audio original, credenciales ni texto completo de usuario en registros técnicos o trazas de evaluación.

## Assumptions

- El portal web existente es la interfaz de cliente para esta entrega; el navegador solicita permiso de micrófono. Esta entrega cubre la grabación desde el botón del chat; la selección y carga de archivos de audio queda fuera del alcance.
- Se requiere una sesión autenticada, igual que para usar el chat existente.
- El idioma principal de uso y de los mensajes de interfaz es español. El sistema conserva el idioma reconocido cuando el servicio lo permite, sin prometer compatibilidad universal.
- El audio se procesa de forma temporal. Solo el texto se incorpora al turno normal y sigue la política de historial vigente.
- La grabación tendrá una duración máxima de 120 segundos y un tamaño máximo de 25 MB (25.000.000 bytes). El límite de tamaño conservador evita depender de las diferencias entre los planes publicados por el proveedor; se valida también en el servidor.
- El servicio de transcripción solicitado es Groq con el modelo `whisper-large-v3-turbo`; su indisponibilidad no habilita una respuesta alternativa inventada ni cambia el patrón seleccionado.
- No se requiere modificar el esquema de base de datos para almacenar el audio; cualquier necesidad de persistir transcripciones fuera de las reglas existentes deberá tratarse en un alcance posterior.
- La transcripción se envía automáticamente al flujo multiagente como mensaje del cliente al finalizar correctamente; no se requiere una pantalla de confirmación antes de procesarla.
- La transcripción debe respetar el máximo de 2.000 caracteres del contrato de chat existente; no se recortan palabras ni contenido de forma automática.
