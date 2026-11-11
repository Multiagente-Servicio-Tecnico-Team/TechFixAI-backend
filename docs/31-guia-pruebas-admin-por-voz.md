# 31. Guía de pruebas: operar como ADMIN por voz

Esta guía explica cómo pedirle al asistente ADMIN, hablando, que consulte datos o
haga operaciones del taller (registrar un asiento contable, ajustar stock, exportar
un reporte, etc.), y cómo probarlo paso a paso.

## Cómo funciona

1. Grabas una orden en el chat ADMIN (o la escribes). El audio se transcribe y se
   procesa exactamente igual que un mensaje escrito.
2. El modelo elige **una** capacidad de una lista cerrada (allowlist) y propone los
   argumentos. Nunca escribe SQL ni ejecuta nada por su cuenta.
3. **Lecturas** (consultar, listar, exportar): se responden de inmediato. No cambian datos.
4. **Escrituras** (crear, actualizar, registrar, anular, confirmar pago…): el backend
   valida los datos y muestra una **propuesta**. No se cambia nada todavía.
5. Respondes **«Confirmo»** (por voz o texto) y el backend vuelve a validar y ejecuta
   la operación **una sola vez**, registrándote como actor. **«Cancelo»** la descarta.

Reglas de seguridad que conviene probar:

- Solo una sesión con rol `ADMIN` puede usar estas rutas; un CUSTOMER o TECHNICIAN
  recibe 403 aunque lo pida por voz.
- La propuesta vence a los **5 minutos** y vive en memoria: un reinicio del servidor
  la descarta (hay que volver a dictarla).
- Cualquier mensaje que **no** sea una confirmación o cancelación explícita (por
  ejemplo, una corrección o una pregunta nueva) **descarta la propuesta pendiente**
  sin ejecutarla.
- Repetir «Confirmo» sobre una propuesta ya ejecutada no la repite.

## Requisitos

En el `.env` del backend:

```
GROQ_API_KEY=...                  # también se usa para transcribir (Whisper en Groq)
AUDIO_TRANSCRIPTION_ENABLED=true
AUDIO_MAX_DURATION_MS=120000      # grabaciones de hasta 2 minutos
AUDIO_REQUESTS_PER_MINUTE=10
```

- Inicia sesión con una cuenta ADMIN (en la BD local de desarrollo: `admin@gmail.com`).
- En el frontend abre el chat ADMIN (`src/features/chat/AdminChat.jsx`), elige un
  patrón y usa el botón de micrófono.
- Cuota de Groq: el plan gratuito tiene un límite diario de tokens por modelo
  (200 000 TPD para `openai/gpt-oss-20b`). Cada orden ADMIN consume ~2 000 tokens
  porque el prompt incluye los campos de todas las capacidades. Si aparece
  «El proveedor LLM no pudo procesar el mensaje», revisa si se agotó la cuota.

## Frases para confirmar o cancelar

| Dices | Resultado |
|---|---|
| «Confirmo.» / «Sí, confirmo.» / «Confirmo la operación.» / «Confirmo la propuesta.» / «Ejecuta la propuesta.» | Ejecuta la propuesta pendiente |
| «Cancelo.» / «No, cancelo.» / «Cancelo la propuesta.» / «Cancela la propuesta.» | Descarta la propuesta |
| «Sí», «ok», «dale», «confirmo pero cambia el monto…» | **No** confirma; se trata como un mensaje nuevo y la propuesta se descarta |

La puntuación que agrega la transcripción («Confirmo.», «¡Cancelo!») se ignora.

## Capacidades disponibles y frases de ejemplo

Los IDs de ejemplo corresponden a la BD local de desarrollo (cliente 1, repuesto 1 con
stock 10, proveedor 3, categoría contable 2 «Servicio técnico», cuentas imputables
`101` Caja y `70321` Servicios – Terceros). Ajusta los valores a tus datos.

### Consultas (sin confirmación)

| Capacidad | Frase de ejemplo |
|---|---|
| `customers.list` / `customers.get` | «Busca el cliente Joseph.» / «Muéstrame el cliente 1.» |
| `tickets.list` / `tickets.get` | «Lista los tickets en estado NEW, solo 3.» / «Muéstrame el ticket 13.» |
| `inventory.list` | «¿Qué procesadores Intel hay en inventario?» |
| `suppliers.list` / `suppliers.get` | «Lista los proveedores.» / «Muéstrame el proveedor 3.» |
| `purchases.list` / `purchases.get` | «Muéstrame las compras pendientes del proveedor 3.» |
| `purchase_orders.list` / `.get` | «Lista las órdenes de compra en borrador.» |
| `sales_quotes.list` / `.get` | «Muéstrame las cotizaciones pendientes del cliente 1.» |
| `sales_orders.list` / `.get` | «Lista los pedidos de venta del cliente 1.» |
| `payments.list` | «¿Qué pagos están pendientes?» |
| `accounting.categories.list` | «Muéstrame las categorías contables.» |
| `accounting.entries.list` / `.get` | «Lista los asientos confirmados.» / «Muéstrame el asiento 3.» |
| `accounting.reports.export` | «Exporta el libro diario de noviembre de 2026 en Excel.» / «Exporta el libro mayor de la cuenta 101 de noviembre en CSV.» / «Exporta el balance de comprobación del 1 al 30 de noviembre de 2026.» |

La exportación devuelve un enlace al endpoint de reportes que ya existía
(`/api/admin/accounting/reports/{journal|ledger|trial-balance}?...&format=xlsx|csv`).
Ábrelo con el **origen del backend** (por ejemplo `http://localhost:8000` + la ruta)
en el mismo navegador donde iniciaste sesión como ADMIN; la cookie autoriza la descarga.

### Escrituras (propuesta + «Confirmo»)

| Capacidad | Frase de ejemplo |
|---|---|
| `accounting.entries.create` | «Registra un asiento contable con fecha 2026-11-09, concepto Servicio de reparación, detalle Cobro en efectivo del ticket TCK-123, categoría 2, debe 150 soles a la cuenta 101 y haber 150 soles a la cuenta 70321.» |
| `accounting.entries.reverse` | «Anula el asiento 3 con fecha 2026-11-09 porque se registró dos veces.» |
| `inventory.adjust_stock` | «Ajusta el stock del repuesto 1: el sistema dice 10 y conté 9 porque uno llegó dañado.» |
| `inventory.create` | «Crea el repuesto SSD-KIN-1TB, SSD Kingston NV2 1TB, categoría Almacenamiento, precio 249.90, stock 5, mínimo 2.» |
| `inventory.update` | «Cambia el precio del repuesto CPU-INT-I3-12100F a 389.90.» |
| `suppliers.create` | «Crea un proveedor llamado Distribuidora Andina con RUC 20123456789 y 5 días de entrega.» |
| `suppliers.update` | «Cambia el teléfono del proveedor 3 a 987654321.» |
| `customers.create` / `customers.update` | «Registra el cliente Carla Ríos con teléfono 912345678.» / «Cambia el correo del cliente 2 a test2@gmail.com.» |
| `tickets.create` / `tickets.update` | «Crea un ticket para Carla Ríos, teléfono 912345678, título Laptop no enciende, falla No enciende desde ayer, tipo reparación.» / «Pasa el ticket 13 a estado IN_DIAGNOSIS.» |
| `purchase_orders.create` | «Crea una orden de compra al proveedor 3 por 10 unidades del repuesto 1 a 300 soles cada una.» |
| `purchase_orders.issue` / `.cancel` | «Emite la orden de compra 2.» / «Cancela la orden de compra 2 porque el proveedor no tiene stock.» |
| `purchase_orders.receive` / `purchases.receive` | «Recibe la orden de compra 2: llegaron 10 unidades del repuesto 1.» |
| `purchases.create` / `.update` / `.cancel` | «Registra la factura F001-123 del proveedor 3 del 2026-11-09, transferencia, pagada, 10 unidades del repuesto 1 a 300.» |
| `sales_quotes.create` | «Crea una cotización para el cliente 1 con 1 unidad del repuesto 2, válida hasta el 2026-11-20.» |
| `sales_quotes.accept` / `.cancel` | «Registra que el cliente aceptó en tienda la cotización 7.» / «Cancela la cotización 7.» |
| `sales_quotes.confirm_payment` | «Confirma el pago de la cotización 7 en efectivo.» |

Cada escritura se valida con el mismo esquema que el endpoint REST equivalente. Si
faltan campos obligatorios o alguno tiene un formato inválido, el chat pregunta cuáles
debes completar o corregir y conserva un borrador en esa conversación. Todavía no se
crea ni modifica nada. Cuando los datos estén completos, verás una propuesta; solo
«Confirmo» la ejecuta.

## Completar datos faltantes

Prueba un alta sencilla hablando o escribiendo:

1. Di: «Quiero registrar un proveedor.»
2. El asistente debe preguntar el nombre del proveedor. No debe mostrar solo el menú
   general ni crear un proveedor.
3. Responde: «Se llama Distribuidora Andina.»
4. El asistente debe conservar la intención de crear el proveedor y mostrar una
   propuesta con ese nombre. Todavía no hay escritura.
5. Di «Confirmo» para crear el registro, o «Cancelo» para descartarlo.

Prueba campos dentro de una lista de artículos:

1. Di: «Crea una orden de compra al proveedor 3.»
2. El asistente debe pedir las líneas faltantes e indicar los datos necesarios de cada
   artículo, como descripción, cantidad y costo unitario.
3. Responde: «Agrega el repuesto 1, SSD Kingston NV2 de 1 TB, 10 unidades a 230 soles
   cada una.»
4. El asistente debe combinar esos datos con el proveedor ya indicado y mostrar la
   propuesta completa. Revisa cada dato antes de confirmar.
5. Di «Confirmo» para ejecutar, o «Cancelo» para terminar sin cambios.

## Corregir formatos, enumeraciones y referencias

Este flujo comprueba que el backend explique el error concreto, conserve los otros
campos y vuelva a validar antes de proponer:

1. Di: «Crea un ticket para Carla Ríos, teléfono 123, correo carla@@gmail.com,
   título Laptop no enciende, falla No enciende desde ayer, tipo nuevo.»
2. El chat debe indicar que el teléfono requiere 9 dígitos, mostrar opciones aceptadas
   para el tipo de ticket y señalar que el correo no tiene formato válido. No debe
   presentar una propuesta ni crear el ticket.
3. Responde: «El teléfono es 987654321, el correo carla@gmail.com y el tipo es
   Reparación.» Debe conservar nombre, título y falla, revalidar y mostrar una
   propuesta completa para el ticket manual, sin exigir una cuenta de acceso.
4. Di «Confirmo» solo después de revisar la propuesta. Si la corrección sigue siendo
   inválida, debe explicar lo que queda por corregir sin cambiar la base de datos.

Para una referencia inexistente, inicia otra conversación y pide: «Crea una
cotización para el cliente 999999 con una unidad del repuesto 2, válida hasta el
2026-11-20.» El backend debe rechazar la referencia antes de proponer; responde con el
ID correcto de un cliente existente y comprueba que vuelve a validar el mismo borrador.

Las aclaraciones funcionan igual por voz y teclado. El correo valida sintaxis, no la
existencia del buzón. Teléfono de cliente/ticket: 9 dígitos peruanos (se admite `+51`);
teléfono de proveedor: 7–15 dígitos en formato internacional.

En un asiento contable, prueba una cuenta no existente o no imputable, por ejemplo:
«Registra un asiento contable con fecha 2026-11-09, concepto Prueba, detalle Prueba
de validación, categoría 2, debe 150 soles a la cuenta 999999 y haber 150 soles a la
cuenta 70321.» El backend debe indicar que la cuenta de la línea no está disponible
para el plan/fecha y conservar el resto del asiento. Corrige el código con una cuenta
imputable vigente (por ejemplo, 101 si está habilitada en tu plan); solo entonces debe
mostrar la propuesta para confirmar.

En ambos casos puedes responder por voz o teclado. Si corriges un dato mientras el
asistente pregunta por información faltante, vuelve a validar el borrador. Si ya había
una propuesta completa, cualquier mensaje distinto de «Confirmo» o «Cancelo» la
descarta; vuelve a formular la operación completa para generar otra propuesta.

## Guion de prueba sugerido

Usa una sola conversación del chat ADMIN y dicta cada paso:

1. «Muéstrame las categorías contables.» → lista de categorías (sin propuesta).
2. «Registra un asiento contable … (frase completa de arriba).» → **Propuesta**
   `accounting.entries.create` con las dos líneas en `150.00`.
3. «Cancelo.» → «La propuesta se canceló. No se hicieron cambios.»
4. Repite el paso 2 y responde «Confirmo.» → «Operación ejecutada…» con el número de
   asiento. Verifica en `GET /api/admin/accounting/entries`.
5. «Confirmo.» otra vez → «Esta propuesta ya se ejecutó; no se repitió la operación.»
6. «Exporta el libro diario de noviembre de 2026 en Excel.» → enlace de descarga;
   ábrelo con el origen del backend y comprueba que el asiento aparece en el XLSX.
7. «Ajusta el stock del repuesto 1: el sistema dice 10 y conté 9 porque uno llegó
   dañado.» → propuesta con `stock_actual` y `stock_final`.
8. Antes de confirmar, di «Mejor que sean 8.» → la propuesta anterior se descarta y
   se genera una nueva; confirma solo la nueva.
9. Espera más de 5 minutos con una propuesta abierta y di «Confirmo.» → 409 «La
   propuesta venció».
10. Inicia sesión como CUSTOMER e intenta `POST /api/admin/chat` → 403.

## Probar sin el frontend

Texto:

```bash
curl -s -b cookies.txt -H "Content-Type: application/json" -X POST http://localhost:8000/api/admin/chat -d '{"pattern":"hierarchical","message":"Exporta el libro diario de noviembre de 2026 en Excel."}'
```

Confirmar una propuesta (usa `conversation_id` y `proposal.proposal_id` de la respuesta
anterior):

```bash
curl -s -b cookies.txt -H "Content-Type: application/json" -X POST http://localhost:8000/api/admin/chat -d '{"pattern":"hierarchical","conversation_id":"<id>","action":"confirm","proposal_id":"<proposal_id>"}'
```

Audio (multipart; `request_id` es un UUID nuevo por grabación y `duration_ms` la
duración en milisegundos):

```bash
curl -s -b cookies.txt -X POST http://localhost:8000/api/admin/chat/audio -F "audio=@orden.webm;type=audio/webm" -F "duration_ms=6000" -F "pattern=hierarchical" -F "request_id=6f1c2c1e-6a36-4e5b-9a2f-2f1d5c7e9b10"
```

`cookies.txt` debe contener la cookie de sesión de una cuenta ADMIN (iniciar sesión con
`POST /auth/login` usando `-c cookies.txt`).

## Limitaciones conocidas

- **Una operación por mensaje.** «Crea el proveedor y luego emite la orden» debe
  dictarse en dos mensajes.
- **Borradores incompletos:** permanecen hasta 5 minutos en la memoria del proceso y
  solo dentro de la conversación, ADMIN y patrón que los iniciaron. Cancelar o cambiar
  a otra operación los descarta sin efectos de negocio. Un reinicio o una instancia
  distinta de Render pierde el borrador; vuelve a formular la operación completa.
- **Importes dictados.** Di los importes como números («150 soles», «249 con 90»); el
  backend los normaliza a dos decimales. Si la transcripción produce palabras
  («ciento cincuenta»), revisa la propuesta antes de confirmar.
- **Cuentas contables** se indican por **código** (`101`, `70321`). Si el modelo sugiere
  un `account_id`, se descarta y la cuenta se resuelve por código en el catálogo.
- **Exportar** no requiere confirmación porque no modifica datos; devuelve un enlace,
  no el archivo.
- No hay capacidades para lo que el backend no expone (por ejemplo, borrar asientos o
  enviar correos); el asistente responde que no está disponible.
