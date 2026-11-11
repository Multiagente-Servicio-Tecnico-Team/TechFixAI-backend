# Guía de pruebas manuales: chat de cliente y ADMIN

Esta guía contiene mensajes copiables y el flujo conversacional completo para probar las capacidades disponibles en el portal y en el taller. Cubre Jerárquico, Orquestador y Descentralizado.

## Cómo usar los ejemplos

- Copia cada mensaje entre comillas tipográficas en el chat. Sustituye cada marcador como <ID REAL> por un valor de prueba existente; no escribas literalmente el marcador.
- Las respuestas del modelo pueden variar de redacción. Valida permisos, datos y efectos, no que responda palabra por palabra.
- Empieza una conversación nueva para cada caso y conserva el mismo patrón durante todo el flujo. Repite los recorridos CUSTOMER con Jerárquico, Orquestador y Descentralizado para comparar los grafos.
- El chat ADMIN se atiende mediante `AdminChatService` y capacidades administrativas compartidas; el selector de patrón no ejecuta cada grafo de cliente. Repetir A01–A18 con otro selector comprueba la interfaz, pero no cuenta como una comparación independiente de los tres grafos.
- En cada caso, lee la parte **Asistente debe** antes de empezar: describe el resultado esperado sin exigir una frase literal. Si el asistente pide datos, contesta con los valores de prueba indicados y sigue el turno siguiente.
- En operaciones ADMIN, el resumen es una propuesta. Revisa campos, IDs, importes y cantidades. Confirma con el botón Confirmar cambio o, en otro turno, escribe “Confirmo la propuesta exactamente como aparece”. Para voz, dicta la confirmación en un turno posterior. Para abortar, usa Cancelar o “Cancelo la propuesta. No hagas ningún cambio”.
- Una consulta distinta o una corrección descarta la propuesta pendiente. Si se pierde la conversación o vence la propuesta, vuelve a formular la operación.
- Antes de escribir, obtén IDs reales desde las consultas o pantallas. No inventes códigos, precios, saldos, disponibilidad ni referencias de pago.

## Preparación

1. Ejecuta backend y frontend locales con datos de prueba. Comprueba que el portal llama al backend y no muestra datos de demostración.
2. Prepara un CUSTOMER vinculado a un perfil comercial, un ADMIN, un TECHNICIAN y un segundo CUSTOMER para probar aislamiento. Usa datos desechables y nombres/códigos únicos; las pruebas administrativas sí escriben en la base.
3. Prepara inventario con stock, una garantía vigente, un pago completado de prueba, y proveedores, compras, órdenes y datos contables de prueba.
4. CUSTOMER usa /portal/asistente y /portal/tickets. ADMIN usa /taller/asistente. No compartas conversaciones entre roles.
5. Para voz, habilita transcripción en el backend y permiso de micrófono en el navegador. Pulsa el micrófono, habla y vuelve a pulsarlo para enviar. Revisa la transcripción. Un error de audio no cuenta como operación ejecutada.

## Alcance funcional

CUSTOMER puede consultar el RAG, buscar productos, pedir tickets de servicio, ver diagnósticos, generar/aceptar cotizaciones, consultar tickets y garantías propias, registrar preferencias logísticas y solicitar revisión de un reembolso. Venta directa y PC_BUILD generan cotizaciones sin ticket de reparación; aceptar no equivale a pagar. Sus preguntas de conocimiento usan el corpus Markdown común.

ADMIN puede consultar clientes, tickets, inventario, proveedores, compras, órdenes de compra, cotizaciones/pedidos/ventas/pagos y asientos/categorías contables. Puede proponer alta/edición de clientes, tickets, repuestos, ajustes de stock, proveedores, compras, órdenes, cotizaciones de venta, aceptación/cancelación de ofertas, confirmaciones de pago y asientos/reversiones. Toda escritura requiere confirmación del mismo ADMIN.

El chat ADMIN no consulta el RAG de preguntas frecuentes: puede explicar de forma general qué recursos administrativos gestiona, pero no debe inventar respuestas factuales como una ubicación. Tampoco borra registros, gestiona el catálogo de cuentas o los periodos, exporta informes, cobra mediante una pasarela ni resuelve/paga reembolsos; esas funciones se hacen en sus pantallas administrativas.

## Guiones de preguntas frecuentes CUSTOMER (solo lectura)

Estos recorridos comprueban los temas presentes en `app/agents/jerarquico/knowledge_base/faq_servicio.md`. En el entorno de prueba el asistente debe comunicar directamente los datos configurados en ese archivo, sin anteponer que son demostrativos. Los valores son provisionales: reemplaza el contenido del Markdown antes de usarlo como información del negocio en producción. Ninguno de estos turnos crea registros, salvo cuando el recorrido indica continuar en C04.

### FAQ-C01 — Ubicación, cómo llegar y horario

1. **Tú:** `Hola, ¿dónde están ubicados?`
2. **Asistente debe:** responder con la dirección configurada, Av. Los Talleres 450, San Borja, Lima, Perú, y puede sugerir buscar “TechFix, Av. Los Talleres 450, San Borja” en una aplicación de mapas.
3. **Tú:** `¿Cuál es el horario habitual de atención?`
4. **Asistente debe:** indicar lunes a viernes de 09:00 a 18:00, sábados de 09:00 a 13:00, domingos y feriados cerrado, hora de Lima.
5. **Tú:** `Si elijo retiro presencial, ¿eso confirma que ya recibieron mi equipo?`
6. **Asistente debe:** distinguir la preferencia de retiro de la recepción física; no afirmar que el equipo fue recibido ni generar un ticket.

**Termina cuando:** verificas la dirección y el horario frente al Markdown y confirmas que no se creó un ticket.

### FAQ-C02 — Cómo obtener una cotización de productos

1. **Tú:** `¿Cómo puedo obtener una cotización para una memoria RAM y una SSD?`
2. **Asistente debe:** explicar que primero consulta las opciones, precio y stock actuales; luego eliges una opción por producto y cantidad; antes de aceptar puedes revisar la propuesta. La cotización se guarda al aceptarla explícitamente.
3. **Tú:** `¿Si acepto significa que ya pagué?`
4. **Asistente debe:** aclarar que aceptar la oferta no confirma el pago; el pago queda pendiente hasta que ADMIN confirme el cobro y se complete el flujo de venta.
5. **Tú:** `Quiero hacerlo ahora. Cotiza una RAM de 8 GB para laptop y una SSD SATA de 480 GB. Primero muéstrame opciones con stock.`
6. **Asistente debe:** consultar ambos productos. Si el resultado es amplio, pedir criterios para cada producto por separado; si no hay coincidencias, explicar cuál criterio no produjo resultados y pedir que lo ajustes, sin mezclar los productos.
7. **Tú:** responde usando lo que el asistente realmente mostró. Ejemplo: `Para la RAM elijo <NOMBRE EXACTO DE LA OPCIÓN>. Para la SSD elijo <NOMBRE EXACTO DE LA OPCIÓN>. Una unidad de cada una; prepara la cotización.`
8. **Asistente debe:** mostrar productos, cantidades y total vigente, y pedir aceptación explícita si corresponde.
9. **Tú:** `Sí, acepto la cotización por el total que acabas de mostrar.`
10. **Asistente debe:** devolver la referencia/estado de la cotización aceptada y explicar que el pago sigue pendiente. Continúa en C04 para validar persistencia, reserva y consulta en Mis compras.

### FAQ-C03 — Servicios y diagnóstico preliminar

1. **Tú:** `¿Qué servicios ofrecen para una laptop que se apaga sola?`
2. **Asistente debe:** explicar que puede orientar sobre reparación/soporte y que el diagnóstico por chat es preliminar; no asegurar una causa ni reparación sin inspección.
3. **Tú:** `¿Pueden confirmar por chat qué componente está dañado?`
4. **Asistente debe:** aclarar que no puede confirmar una falla física sin revisar el equipo y ofrecer registrar un caso de servicio si necesitas seguimiento.
5. **Tú:** `Sí, quiero que revisen mi laptop <MARCA Y MODELO>. Se apaga al iniciar Windows y empezó <CUÁNDO>.`
6. **Asistente debe:** iniciar la recopilación de datos del ticket. Continúa con C05 para completar, confirmar y anotar el ticket; después usa C06 para revisar el diagnóstico guardado.

### FAQ-C04 — Tarifas y precio final

1. **Tú:** `¿Qué tarifas de mano de obra tienen para diagnóstico, mantenimiento y armado de PC?`
2. **Asistente debe:** comunicar las tarifas base cargadas en el FAQ (diagnóstico S/ 50.00, mantenimiento/reparación con trabajo definido S/ 35.00 y armado S/ 50.00) como la información configurada para esta prueba.
3. **Tú:** `¿Ese es siempre el total final, incluidos los repuestos?`
4. **Asistente debe:** indicar que no: el total se confirma en la cotización con la mano de obra aplicable y los precios actuales del catálogo. No inventar descuentos ni precios de productos.
5. **Tú:** `Quiero saber el total de mi caso; el equipo es <MARCA Y MODELO> y la falla es <SÍNTOMA>.`
6. **Asistente debe:** continuar por el flujo de servicio y solicitar solo los datos faltantes. Usa C05–C07 para completar el ticket y cotización de servicio.

### FAQ-C05 — Métodos de pago

1. **Tú:** `¿Qué tipo de pagos aceptan?` (también prueba `¿Qué métodos de pago aceptan?` en cada patrón CUSTOMER).
2. **Asistente debe:** mencionar Yape, Plin, transferencia, tarjetas Visa/Mastercard y efectivo en tienda, según el archivo de conocimiento.
3. **Tú:** `¿Me das el número de cuenta, QR o me confirmas el pago por este chat?`
4. **Asistente debe:** no inventar cuenta ni QR, no solicitar PIN/clave/código de seguridad y explicar que el chat no procesa ni confirma el pago; el canal se coordina al confirmar la compra.

### FAQ-C06 — Garantía y reclamo

1. **Tú:** `¿Qué garantía tiene un armado de PC?`
2. **Asistente debe:** explicar que el flujo descrito asigna una garantía de 3 meses a armados pagados vinculados al pedido; la vigencia individual se consulta con el código de póliza.
3. **Tú:** `¿Y si mi equipo presenta una falla, queda aprobado automáticamente el reclamo?`
4. **Asistente debe:** indicar que no; la cobertura depende de la póliza y de la revisión. Si quieres registrar el caso, continúa con C13 y C14 usando una garantía y un ticket propios elegibles.

### FAQ-C07 — Retiro y courier

1. **Tú:** `¿Puedo pedir envío por courier o retirar en tienda?`
2. **Asistente debe:** explicar las dos preferencias disponibles y que los costos/tiempos del courier se coordinan.
3. **Tú:** `Si elijo courier, ¿ya queda enviado y puedo rastrearlo?`
4. **Asistente debe:** aclarar que registrar preferencia no confirma despacho, seguimiento, costo ni fecha. Para registrar una preferencia de un ticket propio, continúa con C15.

### FAQ-C08 — Productos disponibles

1. **Tú:** `¿Tienen memoria RAM DDR4 de 8 GB en stock?`
2. **Asistente debe:** consultar el inventario actual, o pedir criterios si hay muchas opciones; no responder con precios o existencias aprendidos del FAQ.
3. **Tú:** si solicita acotar, contesta con criterios que aparecieron en la lista, por ejemplo: `Para laptop, marca Kingston; muéstrame solo DDR4 de 8 GB.`
4. **Asistente debe:** mostrar solo coincidencias vigentes o indicar que no encontró. Continúa con C03 para selección y C04 para cotizar; la consulta sola no crea nada.

# Recorridos CUSTOMER

Ejecuta cada recorrido en una conversación nueva. Repite C01–C20 con cada patrón.

## C01 — Consulta técnica con RAG

1. Envía:
   > Mi laptop se calienta y se apaga. ¿Qué comprobaciones básicas y seguras puedo hacer antes de llevarla al taller?
2. Continúa:
   > ¿Qué señales debería anotar para explicarle mejor la falla al técnico?

**Comprobar:** respuesta orientativa respaldada por conocimiento disponible; no afirma una inspección física, una causa confirmada, precio o compatibilidad sin evidencia. No crea ticket ni cotización.

## C02 — Dato operativo no documentado (abstención)

1. Envía:
   > ¿Cuál es la dirección y el horario oficial de la sede de Arequipa?
2. Si pregunta qué sede, aclara:
   > La sede de Arequipa. Necesito la dirección exacta y el horario de hoy.

**Comprobar:** el corpus contiene una dirección de San Borja, pero no una sede en Arequipa. No debe inventar la segunda sede ni su dirección/horario/teléfono. No modifica registros.

## C03 — Búsqueda amplia y acotación

1. Envía:
   > Quiero comprar una memoria RAM de 8 GB. Muéstrame opciones con stock.
2. Si pide acotar, elige criterios que realmente aparezcan en su respuesta. Ejemplo:
   > Es para laptop, DDR4 y de marca Kingston. Busca solo artículos que cumplan esos criterios.
3. Si lista coincidencias, elige una:
   > Quiero revisar la opción <NÚMERO O NOMBRE EXACTO QUE MOSTRÓ> y saber su precio y stock actual.

**Comprobar:** opciones, precio y existencias provienen del catálogo vigente. Si no hay coincidencias, no inventa artículos ni mezcla el mensaje anterior con el nuevo. Este recorrido solo consulta; no crea ticket ni cotización.

## C04 — Venta directa: cotizar y aceptar

1. Solicita una cotización con más de un producto:
   > Quiero cotizar una memoria RAM de <CAPACIDAD> GB y una SSD <INTERFAZ O CAPACIDAD>. No elijas variantes todavía; muéstrame las opciones con stock para cada producto.
2. Si pide acotar, da criterios para cada producto usando opciones que realmente aparecieron. Ejemplo:
   > La RAM es para laptop, DDR4 y de marca <MARCA QUE APARECIÓ>. La SSD debe ser <INTERFAZ QUE APARECIÓ>, capacidad <CAPACIDAD>. Busca ambos criterios por separado.
3. Elige una opción real para cada producto:
   > Para la RAM elijo <NOMBRE O CÓDIGO MOSTRADO>, cantidad <CANTIDAD>. Para la SSD elijo <NOMBRE O CÓDIGO MOSTRADO>, cantidad <CANTIDAD>. Prepara una sola cotización con esas líneas.
4. Revisa importe y líneas. Para aceptar explícitamente:
   > Sí, acepto la cotización por el total que acabas de mostrar.
5. Revisa Mis cotizaciones y el estado de la operación en Mis compras.

**Comprobar:** cotización de venta sin ticket de reparación. Al aceptarla se revalidan precio/stock y se reserva según la regla vigente; el pago queda pendiente. No debe informar que ya recibió el pago.

## C05 — Crear un ticket de reparación

1. Envía:
   > Quiero ingresar al taller mi laptop Lenovo ThinkPad E14. Se apaga al iniciar Windows y necesito que revisen la falla. Registra un caso de reparación con estos datos.
2. Si pide un dato, responde con un dato de prueba, por ejemplo:
   > Es una laptop y la falla ocurre desde ayer. El número de serie de prueba es <SERIE DE PRUEBA>.
3. Si el patrón pide confirmar la recepción, revisa el resumen y responde:
   > Sí, confirmo que esos son los datos del ticket de reparación.
4. Anota el código que devuelve y abre Mis Tickets.

**Comprobar:** ticket REPAIR vinculado al CUSTOMER autenticado, con código estable. No debe inventar datos de contacto ni convertirlo en una venta.

## C06 — Completar diagnóstico y verlo en el portal

1. Continúa C05. Describe únicamente síntomas observados:
   > El equipo se apaga al iniciar y antes escuché el ventilador acelerado. Continúa con una evaluación técnica preliminar.
2. Responde las aclaraciones que solicite. Después abre o actualiza Mis Tickets y despliega el ticket de C05.

**Comprobar:** la tarjeta muestra el tipo y el texto de diagnóstico hardware/software persistido por el backend. El diagnóstico es preliminar; no se presenta como causa confirmada. El ADMIN también lo puede contrastar en el detalle del ticket.

## C07 — Aceptar cotización de servicio

1. En la conversación de C05/C06, revisa la propuesta y el total.
2. Si la aceptas, envía en un turno aparte:
   > Sí, confirmo y acepto la cotización de servicio por el total mostrado para el ticket <CÓDIGO DEL TICKET>.
3. Revisa Mis Tickets y el detalle administrativo.

**Comprobar:** cotización REPAIR ligada al mismo ticket, pago PENDING y estado de ticket de pago pendiente. El servicio no reserva inventario. El código de ticket no cambia.

## C08 — Rechazar cotización de servicio

1. En una conversación nueva, completa C05 y espera la propuesta.
2. Envía:
   > No acepto esta cotización. Deja el ticket abierto para seguimiento y no registres un pago.
3. Revisa Mis Tickets.

**Comprobar:** el ticket de servicio permanece abierto; no se crea pago ni cotización aceptada. El rechazo no crea otro ticket.

## C09 — Precio o stock cambió antes de aceptar

1. Como CUSTOMER, inicia una reparación con un repuesto real y deja pendiente la cotización.
2. En otra sesión, como ADMIN, cambia el precio o stock de ese artículo.
3. Vuelve a la sesión CUSTOMER y envía:
   > Sí, acepto la cotización pendiente por el importe que aparecía antes.
4. Revisa el mensaje y Mis Tickets. No confirmes de nuevo una propuesta que indique que está obsoleta.

**Comprobar:** el backend revalida precio y disponibilidad. No debe guardar la cotización/pago con valores anteriores si la propuesta cambió; puede pedir que revises una nueva cotización. El ticket permanece. Registra el resultado observado si el artículo usado no activa la condición de conflicto.

## C10 — Armado de PC como cotización

1. Envía:
   > Quiero cotizar una PC para juegos con presupuesto máximo de S/ <MONTO DE PRUEBA>. No compres ni confirmes nada todavía.
2. Responde las aclaraciones de uso y presupuesto. Ejemplos:
   > La usaré para juegos en 1080p y ya tengo monitor y teclado.
   >
   > Muéstrame componentes compatibles que estén disponibles y explícame las opciones antes de elegir.
3. Selecciona únicamente artículos listados:
   > Elijo la opción <NÚMERO O NOMBRE MOSTRADO> para <TIPO DE COMPONENTE>.
4. Cuando el resumen esté completo, acepta si corresponde:
   > Sí, acepto la cotización de armado por el total que indicaste.
5. Revisa Mis cotizaciones y el estado del pago.

**Comprobar:** queda como PC_BUILD sin ticket de reparación. Al aceptar se revalida y reserva el stock; el pago sigue PENDING. La propuesta no certifica compatibilidad técnica ni confirma pago.

## C11 — Consultar el estado de un ticket propio

1. Usa un código de Mis Tickets:
   > ¿Cuál es el estado actual de mi ticket <CÓDIGO PROPIO>? Indícame qué seguimiento figura.

**Comprobar:** coincide con Mis Tickets. La respuesta se limita a la sesión autenticada.

## C12 — Aislamiento de dos clientes

1. Entra como CUSTOMER A y anota un ticket propio. Sal de la sesión.
2. Entra como CUSTOMER B y envía:
   > ¿Cuál es el estado y diagnóstico del ticket <CÓDIGO DE CUSTOMER A>?
3. Continúa:
   > Muéstrame también las cotizaciones y pagos de ese ticket.

**Comprobar:** no revela si el registro ajeno existe ni sus datos. Mis Tickets, diagnósticos, cotizaciones, pagos y compras solo muestran datos de B. No se puede elegir titular con un customer_id escrito en el chat.

## C13 — Consultar garantía

1. Con un código de garantía propio:
   > Consulta el estado y la fecha de vencimiento de mi garantía <CÓDIGO DE GARANTÍA PROPIO>.
2. En una conversación aparte, prueba un código ajeno o inexistente:
   > Consulta la garantía <CÓDIGO NO PROPIO>.

**Comprobar:** la lectura propia devuelve el estado de la fuente operativa y no crea reclamo. Para un código ajeno/inexistente no revela datos protegidos.

## C14 — Solicitar revisión de garantía

1. Con un ticket y garantía propios elegibles, envía:
   > Quiero registrar un reclamo de garantía para el ticket <CÓDIGO PROPIO>. La garantía es <CÓDIGO PROPIO>. La falla observada es <DESCRIPCIÓN BREVE>. Solicito revisión; no asumas todavía que está cubierta.
2. Completa los datos faltantes que solicite. Si presenta un resumen, compruébalo y responde:
   > Sí, confirmo que esos son los datos de mi solicitud de revisión de garantía.
3. Anota el código/estado que devuelve. Si después solicita coordinar la recepción, continúa con C15 en esta misma conversación.

**Comprobar:** queda una solicitud pendiente de revisión manual, no una decisión de cobertura ni reparación garantizada. Una garantía vencida o ajena no genera un reclamo elegible.

## C15 — Preferencia logística de un ticket

Opción courier:
1. Envía:
   > Para el ticket <CÓDIGO PROPIO>, prefiero envío por courier. La empresa es <EMPRESA DE PRUEBA> y la dirección es <DIRECCIÓN DE PRUEBA>. Registra la preferencia, no confirmes recepción ni despacho.
2. Si falta un dato, complétalo. Confirma el resumen si lo solicita.

Opción retiro:
1. En otra conversación envía:
   > Para el ticket <CÓDIGO PROPIO>, prefiero coordinar retiro presencial. Registra la preferencia sin marcar el equipo como entregado.

**Comprobar:** preferencia pendiente ligada al ticket propio. No confirma pago, recepción física, despacho ni entrega.

## C16 — Solicitar un reembolso pendiente

1. Usa un pago completado propio preparado para pruebas:
   > Solicito revisar un reembolso del pago <CÓDIGO DE PAGO PROPIO>, por el importe exacto de S/ <IMPORTE DEL REGISTRO>, porque <MOTIVO DE PRUEBA>. Registra solo la solicitud pendiente.
2. Si solicita confirmar datos, revisa código e importe:
   > Confirmo que solicito revisar ese pago y ese importe. Entiendo que la resolución es manual.
3. Repite en conversaciones separadas con un pago pendiente, importe distinto y pago ajeno.

**Comprobar:** solo una solicitud elegible propia queda REQUESTED. No se aprueba ni transfiere dinero. Casos no elegibles no crean solicitud.

## C17 — Compra a proveedor no disponible para CUSTOMER

1. Envía:
   > Compra al proveedor <NOMBRE> el repuesto <NOMBRE DEL REPUESTO> y recíbelo en mi nombre.

**Comprobar:** informa que el chat CUSTOMER no gestiona compras a proveedores y que se puede buscar una alternativa del catálogo. No crea compra, orden, recepción ni reserva.

## C18 — Usar voz como CUSTOMER

1. En /portal/asistente, selecciona un patrón, pulsa el micrófono y dicta:
   > Quiero revisar una laptop que se apaga al iniciar; necesito un ticket de reparación.
2. Vuelve a pulsar para enviar; revisa transcripción y respuesta. Atiende aclaraciones por voz o texto.
3. Si aparece una cotización y quieres aceptarla, hazlo en un segundo turno de voz:
   > Sí, confirmo y acepto la cotización que acabas de mostrar.

**Comprobar:** voz mantiene rol, patrón y conversación. Una solicitud de voz no acepta cotizaciones automáticamente; se necesita una confirmación explícita posterior.

## C19 — Confirmar visibilidad y privacidad del diagnóstico

1. Completa C05 y C06.
2. Actualiza Mis Tickets y busca el mismo código.
3. En otra cuenta CUSTOMER intenta consultar ese ticket.

**Comprobar:** el titular ve el diagnóstico guardado; el otro CUSTOMER no lo ve. Si todavía no hay evaluación, la sección se omite.

## C20 — Solicitar soporte técnico sin reparación definida

1. Envía:
   > Necesito soporte con mi laptop <MARCA Y MODELO>. No logra conectarse al Wi-Fi desde hoy. Quiero que revisen el caso; todavía no sé si requiere reparación.
2. Responde las aclaraciones que pida sobre equipo y síntomas. Si solicita confirmar la recepción del ticket, revisa los datos y contesta:
   > Sí, confirma el ticket de soporte con esos datos.
3. Anota el código, revisa Mis Tickets y deja que el asistente evalúe el caso.

**Comprobar:** se crea un ticket SUPPORT asociado al CUSTOMER autenticado y se persiste/expone el diagnóstico como en C06. No se crea una cotización de venta ni se confirma una reparación no evaluada.

## C21 -- Sin stock en el catálogo

1. **Tú:** `Quiero comprar un SSD 99 TB modelo XYZ`.
2. **Asistente debe:** indicar que no encontró un artículo con stock y precio suficientes, sugerir ajustar capacidad/interfaz/marca o buscar otro producto, y terminar ese flujo.
3. **Comprobar:** no deriva a compras a proveedores ni crea compra, orden o reserva. La búsqueda siguiente debe comenzar como una solicitud nueva.

# Recorridos ADMIN

En `/taller/asistente`, inicia sesión con rol ADMIN. Envía una sola consulta u operación por turno; no combines lecturas ni escrituras distintas en un mismo mensaje. Para comparar el selector puedes cambiar el patrón, pero las operaciones ADMIN usan el servicio y las capacidades compartidas; no recorren los grafos CUSTOMER por separado.

## A00 — Descubrir el chat ADMIN y preparar una cotización desde cero

### Consultar qué operaciones admite

1. **Tú:** `¿Qué puedes consultar y gestionar desde el asistente administrativo?`
2. **Asistente debe:** mencionar clientes, tickets, inventario, proveedores, compras, órdenes, ventas y contabilidad, y señalar que cada escritura se propone y requiere confirmación.
3. **Tú:** `¿Dónde está ubicada la tienda?`
4. **Asistente debe:** no tratar el chat ADMIN como FAQ/RAG ni inventar dirección. Puede responder con el alcance del asistente administrativo. Si necesitas ensayar esa pregunta factual, hazlo en el chat CUSTOMER con FAQ-C01.

### Crear una cotización de venta buscando primero los IDs

1. **Tú:** `Busca el cliente con correo <CORREO DE PRUEBA> y muestra su ID y datos comerciales permitidos. No muestres credenciales.`
2. **Asistente debe:** mostrar el cliente encontrado y su ID comercial. Anota el ID; si hay varios, identifica el correcto antes de seguir.
3. **Tú:** `Busca en inventario <DESCRIPCIÓN DEL PRODUCTO>. Muestra el ID numérico del repuesto, el nombre, el precio y el stock.`
4. **Asistente debe:** devolver artículos actuales. Anota `spare_part_id` numérico y precio; no uses el SKU como reemplazo del ID.
5. **Tú:** `Crea una cotización de venta para el cliente ID <CUSTOMER_ID>. Incluye el repuesto ID <SPARE_PART_ID> en cantidad <CANTIDAD>, con vencimiento <FECHA Y HORA FUTURA ISO 8601 CON ZONA HORARIA> y observación <NOTA DE PRUEBA>. No la aceptes ni registres pago.`
6. **Asistente debe:** presentar una propuesta con cliente, artículo, cantidad, total y vencimiento. Aún no cambia la base.
7. **Tú:** revisa la propuesta y responde `Confirmo la propuesta exactamente como aparece. Ejecuta una sola vez.` Si algún dato no coincide, responde `Cancelo la propuesta. No hagas ningún cambio.`
8. **Asistente debe:** ejecutar una sola vez después de confirmar, devolver el resultado/ID, o informar que se canceló sin cambios.
9. **Tú:** `Muestra la cotización de venta ID <ID DEVUELTO> y su estado de pago.`
10. **Asistente debe:** consultar la cotización y mostrar que la oferta está creada; crearla no implica aceptación ni pago.

**Termina cuando:** verificas el ID y la cotización en la vista administrativa. Para seguir con aceptación presencial y pago confirmado solo si se recibió realmente, continúa con A15.

## A01 — Buscar cliente

1. Envía:
   > Busca el cliente con correo <CORREO DE PRUEBA>, muestra su ID y datos comerciales permitidos. No muestres credenciales.
2. En otro caso:
   > Busca clientes que coincidan con el nombre <NOMBRE DE PRUEBA>.

**Asistente debe:** devolver coincidencias y sus IDs comerciales para poder elegir el registro correcto. Si no encuentra ninguno, decirlo; no crear una cuenta `users` ni revelar credenciales.

**Comprobar:** consulta sin propuesta; no muestra credenciales de users.

## A02 — Consultar tickets

1. Envía:
   > Lista tickets abiertos que coinciden con el cliente <NOMBRE O CORREO REAL>. Incluye código, tipo, estado y equipo.
2. Abre uno de los resultados:
   > Muestra el detalle del ticket ID <ID REAL DE LA LISTA>, incluido el diagnóstico y las cotizaciones.

**Asistente debe:** primero listar tickets que coincidan; después consultar solo el detalle del ID elegido. Si el ticket no existe, informarlo sin modificar nada.

**Comprobar:** los datos coinciden con Banco de reparaciones; no hay cambios.

## A03 — Consultar inventario

1. Envía:
   > Busca en inventario <NOMBRE, MARCA O CÓDIGO REAL>. Muéstrame código, nombre, categoría, precio y stock.
2. Si hay muchos resultados:
   > Filtra por <CRITERIO QUE APARECIÓ> y muestra esas coincidencias actuales.

**Asistente debe:** mostrar los datos vigentes y el ID numérico del repuesto, además del SKU/código cuando esté disponible. Usa ese ID numérico si luego vas a crear una cotización, compra u orden.

**Comprobar:** lectura de inventario vigente, sin modificar stock.

## A04 — Consultar proveedores

1. Envía:
   > Lista proveedores activos y su contacto y plazo de entrega registrados.
2. Para detalle:
   > Muestra el proveedor ID <ID REAL>.

**Asistente debe:** mostrar proveedores registrados y el detalle del ID solicitado. No inferir qué artículos vende ese proveedor ni sus precios o plazos por producto.

**Comprobar:** solo datos registrados; el asistente no inventa ofertas, precio de repuesto ni plazo por producto.

## A05 — Consultar órdenes de compra

1. Envía:
   > Lista las órdenes de compra pendientes, con proveedor, estado, fecha estimada y artículos.
2. Para detalle:
   > Muestra la orden ID <ID REAL>, con cantidades pedidas y recibidas.

**Asistente debe:** separar borradores, emitidas, parciales, recibidas o canceladas según el estado real y devolver cantidades solicitadas/recibidas. Una consulta no emite ni recibe la orden.

**Comprobar:** crear o emitir una orden no suma stock.

## A06 — Consultar compras y comprobantes

1. Envía:
   > Lista compras recibidas con pago pendiente. Muestra proveedor, comprobante, total y estado de pago.
2. Para una compra:
   > Muestra la compra ID <ID REAL> y sus líneas y recepciones.

**Asistente debe:** devolver el comprobante, proveedor, totales, pago y cantidades recibidas disponibles en el registro. No completar datos que falten ni cambiar el estado de pago.

**Comprobar:** no confunde compra/comprobante con orden y no marca pago por consultar.

## A07 — Consultar ofertas, ventas y pagos

1. Envía:
   > Lista cotizaciones de venta pendientes y aceptadas.
2. En otro turno, consulta pedidos:
   > Lista pedidos de venta recientes.
3. En otro turno, consulta pagos:
   > Lista pagos pendientes y muestra su ID, estado, importe y cotización asociada.
4. Para detalle de cotización:
   > Muestra la cotización de venta ID <ID REAL> y su pago asociado, si existe.

**Asistente debe:** mantener separados estado de oferta, aceptación, estado de pago y pedido. Si solicitas un detalle, usa un ID que devolvió la lista.

**Comprobar:** oferta, aceptación, pago y pedido/venta son estados diferentes. Lectura sin escritura.

## A08 — Consultar contabilidad

1. Envía:
   > Lista los últimos asientos contables confirmados con fecha, concepto e importes.
2. Consulta categorías:
   > Lista las categorías contables disponibles.
3. Para un asiento de la primera lista:
   > Muestra el detalle del asiento ID <ID REAL>, incluidos responsable, fecha, concepto y líneas debe/haber.

**Asistente debe:** devolver asientos/categorías existentes y el detalle solicitado; no crear, cambiar ni revertir nada en una consulta.

**Comprobar:** información contable interna; no crea asientos, PLE ni presentación a SUNAT.

## Protocolo de propuesta y confirmación ADMIN

Para A09–A16:
1. Envía el prompt de operación y espera la propuesta.
2. Revisa IDs, datos, importes, fechas, cantidades y líneas.
3. Confirma con el botón Confirmar cambio o en un nuevo turno:
   > Confirmo la propuesta exactamente como aparece. Ejecuta una sola vez.
4. Para cancelar, pulsa Cancelar o envía:
   > Cancelo la propuesta. No hagas ningún cambio.
5. Verifica el resultado en la sección administrativa correspondiente. Si hay un dato equivocado, cancela; no preguntes algo distinto mientras la propuesta deba permanecer pendiente.

## A09 — Crear y editar cliente comercial manual

Crear:
1. Envía valores de prueba únicos:
   > Registra un cliente manual llamado <NOMBRE>, teléfono <TELÉFONO DE PRUEBA> y correo <CORREO DE PRUEBA>. No le crees una cuenta de acceso.
2. Revisa y confirma; anota ID. Comprueba en Clientes.

Editar:
3. Envía:
   > Actualiza el teléfono del cliente ID <ID CREADO> a <NUEVO TELÉFONO DE PRUEBA>.
4. Revisa, confirma y vuelve a consultar.

**Comprobar:** el cliente manual no tiene user ni credenciales. ADMIN autor y cliente atendido son identidades diferentes.

## A10 — Crear y actualizar ticket de servicio

Crear:
1. Obtén un customer_id real con A01. Envía:
   > Crea un ticket manual de reparación para cliente ID <CUSTOMER_ID>. Contacto <NOMBRE>, teléfono <TELÉFONO>, correo <CORREO>. Equipo <MARCA Y MODELO>. Falla observada <SÍNTOMA>. Tipo REPAIR y mano de obra estimada <HORAS> horas. No registres cotización todavía.
2. Revisa cliente, contacto, equipo, tipo y falla. Confirma y anota ID/código.

Editar:
3. Envía:
   > Actualiza el ticket ID <ID REAL> para corregir la descripción de la falla a <DESCRIPCIÓN DE PRUEBA>. No cambies cliente ni estado.
4. Revisa y confirma; consulta el detalle en Banco de reparaciones.

**Comprobar:** no crea cotización automáticamente; el ADMIN queda como autor, no como cliente.

## A11 — Crear/editar repuesto y ajustar existencias

Alta:
1. Envía:
   > Crea un repuesto de prueba con código único <CÓDIGO MAYÚSCULAS>, nombre <NOMBRE>, categoría <CATEGORÍA>, descripción <DESCRIPCIÓN>, precio unitario <PRECIO CON DOS DECIMALES>, stock mínimo <NÚMERO> y stock inicial cero.
2. Revisa y confirma. Busca el artículo y anota el ID.

Editar:
3. Envía:
   > Actualiza el repuesto <CÓDIGO> para cambiar descripción a <DESCRIPCIÓN DE PRUEBA> y stock mínimo a <NÚMERO>.
4. Revisa y confirma.

Ajustar:
5. Consulta las existencias actuales y envía:
   > Ajusta por conteo físico el repuesto ID <ID REAL>: stock esperado <STOCK ACTUAL>, conteo nuevo <STOCK CONTADO>. Motivo: <MOTIVO DE PRUEBA>.
6. Revisa y confirma; abre Movimientos de inventario.

**Comprobar:** ajuste con motivo, actor y movimiento trazable. Si el stock esperado cambió, no confirmes el dato antiguo.

## A12 — Crear y editar proveedor

Crear:
1. Envía:
   > Registra el proveedor de prueba <NOMBRE ÚNICO>, RUC <RUC DE PRUEBA SI DISPONIBLE>, contacto <NOMBRE>, correo <CORREO>, teléfono <TELÉFONO>, dirección <DIRECCIÓN> y plazo de entrega <DÍAS> días.
2. Revisa y confirma; anota ID.

Editar:
3. Envía:
   > Actualiza el proveedor ID <ID REAL>: teléfono <NUEVO TELÉFONO> y plazo de entrega <NUEVO NÚMERO> días.
4. Revisa y confirma; verifica en Compras → Proveedores.

**Comprobar:** cambios auditados y no ejecutados antes de confirmar. Para probar activar/desactivar, pide expresamente active verdadero/falso sobre un proveedor de prueba.

## A13 — Registrar, editar, cancelar y recibir una compra

Registrar:
1. Obtén proveedor y repuesto de A03/A04. Envía:
   > Registra compra al proveedor ID <ID REAL>, comprobante <TIPO>, serie <SERIE>, número único <NÚMERO>, fecha de emisión <FECHA ISO>, vencimiento <FECHA ISO O SIN VENCIMIENTO>, método TRANSFER, estado PENDING. Línea vinculada al repuesto ID <ID REAL>: descripción <NOMBRE>, cantidad <CANTIDAD>, costo unitario <COSTO>, impuesto <IMPUESTO> y descuento 0.00.
2. Revisa y confirma; anota ID de compra y de línea. Comprueba stock antes de recibir.

Editar:
3. Envía:
   > Actualiza la compra ID <ID REAL>: estado de pago PENDING y nota <NOTA DE PRUEBA>.
4. Revisa y confirma. Marca PAID solo cuando registres un pago efectivamente recibido en la prueba.

Recibir:
5. Envía:
   > Registra la recepción de compra ID <ID REAL>. De la línea ID <ID DE LÍNEA>, recibí <CANTIDAD RECIBIDA>. Nota: recepción de prueba.
6. Revisa cantidades, confirma y consulta movimientos de inventario.

Cancelar:
7. En otra compra no recibida y cancelable, envía:
   > Cancela la compra ID <ID REAL>.
8. Revisa y confirma. No uses una compra que ya tenga recepción si el estado no admite cancelación.

**Comprobar:** registrar comprobante no incrementa stock; la recepción es la que suma lo realmente recibido y deja trazabilidad. No duplica movimientos.

## A14 — Crear, emitir, editar, recibir o cancelar orden de compra

Crear:
1. Obtén proveedor y artículo reales. Envía:
   > Crea en borrador una orden de compra para proveedor ID <ID REAL>, llegada estimada <FECHA ISO>, nota <NOTA>. Línea: repuesto ID <ID REAL>, descripción <NOMBRE>, cantidad <CANTIDAD ENTERA>, costo unitario <COSTO CON DOS DECIMALES>.
2. Revisa y confirma. Anota ID de orden e ID de línea. Comprueba que stock no cambió.

Emitir:
3. Envía:
   > Emite la orden de compra ID <ID REAL>. No registres la recepción todavía.
4. Revisa y confirma. Comprueba otra vez que stock no cambió.

Editar borrador:
5. En una orden que siga en borrador:
   > Actualiza la orden ID <ID REAL>: llegada estimada <FECHA ISO> y nota <NUEVA NOTA>.
6. Confirma y verifica. No intentes editar un estado que el backend no permita.

Recepción parcial y saldo:
7. Envía:
   > Registra recepción parcial de la orden ID <ID REAL>. De la línea ID <ID DE LÍNEA>, recibí <CANTIDAD PARCIAL>. Nota: primera entrega de prueba.
8. Revisa y confirma; valida movimiento y stock. Después:
   > Completa la recepción de la orden ID <ID REAL>. De la línea ID <ID DE LÍNEA>, recibí <CANTIDAD RESTANTE> unidades adicionales.
9. Revisa y confirma.

Cancelar:
10. En otra orden de prueba que no se recibió:
   > Cancela la orden ID <ID REAL> por el motivo <MOTIVO DE PRUEBA>.
11. Revisa y confirma.

**Comprobar:** crear, editar, emitir y cancelar no cambian stock. Cada recepción suma solo las cantidades recibidas y una sola vez.

## A15 — Cotización de venta, aceptación, pago y cancelación

Crear:
1. Obtén el customer_id con A01 y el ID numérico de artículo con A03. Envía:
   > Crea una cotización de venta para cliente ID <ID REAL>, con vencimiento <FECHA ISO FUTURA>. Incluye artículo ID <SPARE_PART_ID REAL>, cantidad <CANTIDAD>. Observaciones <NOTA>. No la marques como pagada.
2. Revisa líneas, total y vencimiento; confirma y anota quote_id.

Aceptar manualmente:
3. Envía:
   > Registra la aceptación presencial de cotización ID <QUOTE_ID>, canal IN_PERSON, nota <NOTA>. Esto no confirma que se recibió el pago.
4. Revisa y confirma. Comprueba que pago sigue pendiente.

Confirmar pago:
5. Solo si recibiste realmente el pago en el entorno de prueba, envía:
   > Confirma el pago recibido de cotización ID <QUOTE_ID>, método BANK_TRANSFER, referencia <REFERENCIA REAL DE PRUEBA>, nota <NOTA>.
6. Revisa importe, método y referencia. Confirma; consulta Ventas y el pago.

Cancelar otra oferta:
7. En una cotización de prueba todavía cancelable:
   > Cancela la cotización de venta ID <OTRO QUOTE_ID>, nota <MOTIVO DE PRUEBA>.
8. Revisa y confirma; verifica que cancelarla no registra pago ni venta.

**Comprobar:** oferta, aceptación, pago y pedido/venta se mantienen separados. No inventes referencias de transacción ni confirmes un cobro simulado.

## A16 — Crear y revertir asiento contable

Antes de comenzar, consulta una categoría y obtén cuentas imputables activas y su plan desde Contabilidad → Cuentas. Usa importes ficticios y balanceados.

Crear:
1. Envía dos líneas con importes iguales:
   > Registra un asiento interno de prueba con fecha <FECHA ISO>, concepto <CONCEPTO>, detalle <DETALLE>, categoría ID <CATEGORY_ID REAL> y plan ID <PLAN_ID REAL>. Línea 1: cuenta <CÓDIGO CONTABLE IMPUTABLE>, debe <MONTO>, haber 0.00. Línea 2: cuenta <OTRO CÓDIGO IMPUTABLE>, debe 0.00, haber <EL MISMO MONTO>.
2. Comprueba fecha, categoría, cuentas y que debe=haber. Confirma y anota ID/número.
3. Abre su detalle y valida líneas y actor ADMIN.

Revertir:
4. Envía:
   > Revierte el asiento ID <ID REAL> con fecha <FECHA ISO> y motivo <MOTIVO DE PRUEBA>. Crea un asiento compensatorio vinculado; no borres el original.
5. Revisa y confirma. Comprueba que el original queda y se crea una reversión vinculada.

**Comprobar:** un asiento confirmado no se borra ni modifica; se conserva trazabilidad. Si el periodo está cerrado, respeta el error. El chat no administra periodos.

## A17 — Escribir por voz como ADMIN

1. Graba una consulta de lectura, revisa transcripción y respuesta.
2. En un caso nuevo, dicta una escritura de prueba usando el ID que obtuviste en A04:
   > Prepara una propuesta para actualizar el proveedor ID <ID REAL>: cambia el plazo de entrega a <NÚMERO> días.
3. Revisa la propuesta sin ejecutarla.
4. En otro turno de voz, dicta:
   > Confirmo la propuesta exactamente como aparece.
5. Verifica Proveedores. Repite con una propuesta cancelada.

**Comprobar:** el primer audio solo propone. La confirmación inequívoca posterior del mismo ADMIN y conversación ejecuta una vez.

## A18 — Autorización, cancelación y expiración

1. Como CUSTOMER, intenta abrir /taller/asistente. Debe denegarse.
2. Repite como TECHNICIAN. También debe denegarse.
3. Como ADMIN A, crea una propuesta. Intenta confirmarla desde otra cuenta ADMIN B: no debe ejecutarla.
4. Crea otra y cancélala. Confirma que no hubo cambio.
5. Crea otra, responde “quizás luego” y luego pregunta algo diferente. La propuesta anterior no debe ejecutarse.
6. Intenta confirmar una propuesta vencida o perdida por reinicio. Debe solicitar formular de nuevo la operación.

**Comprobar:** ninguna acción administrativa se ejecuta sin permisos y confirmación inequívoca del actor correcto.

# Registrar resultados

Completa una fila por caso y patrón. Para escrituras registra IDs y estados antes/después. No pegues contraseñas, cookies, claves ni datos personales reales.

| Fecha | Rol | Patrón | Caso | Resultado | Código/estado | Nota |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Si un caso falla o queda bloqueado

- En una búsqueda amplia, responde con los criterios que realmente mostró el asistente; no inventes opciones de catálogo.
- Si falta un ID, detén la escritura y obtén el ID desde una consulta/pantalla. No sustituyas el ID por SKU, código o user_id.
- Un error de proveedor, audio deshabilitado o almacenamiento es “Bloqueado”; no es una operación completada.
- Ante timeout después de enviar una escritura, consulta primero el recurso para descartar que se haya guardado antes de reintentar.
- Registra el error y patrón sin copiar secretos de .env.

