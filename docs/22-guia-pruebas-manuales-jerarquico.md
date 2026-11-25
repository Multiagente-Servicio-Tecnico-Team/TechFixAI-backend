# Guía de pruebas manuales: patrón jerárquico

Esta guía enumera los flujos que el código actual del patrón jerárquico puede ejecutar desde el chat y qué resultado comprobar. Está basada en el grafo de `app/agents/jerarquico/graph/builder.py`, sus agentes y las pruebas automatizadas existentes. Las respuestas del modelo pueden variar; comprueba el resultado funcional y los cambios en el portal/base de datos, no una frase exacta.

## Preparación

1. Inicia el backend desde la carpeta del backend:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host localhost --port 8000 --reload
   ```

2. Inicia el frontend desde su carpeta, por ejemplo en el puerto local configurado:

   ```powershell
   npm run dev -- --host localhost --port 5174 --strictPort
   ```

3. Inicia sesión con una cuenta de cliente. El chat requiere sesión `CUSTOMER`; una sesión administrativa no sirve para probar los flujos de cliente.
4. En una conversación nueva, selecciona **Jerárquico** antes de enviar el primer mensaje. El patrón queda fijado para esa conversación.
5. Usa una conversación nueva para cada caso independiente. Mantén la misma conversación en los pasos de selección, aceptación y logística de cada flujo.
6. Para ventas, debe haber productos activos con stock y precio positivo en PostgreSQL. Para garantías, la cuenta debe tener una póliza propia. Para probar reembolsos, se necesita un pago de esa cuenta con estado `COMPLETED`.

> **Cuidado con los datos:** una venta aceptada, una solicitud de soporte, una preferencia logística, una garantía o una solicitud de reembolso puede escribir registros reales en la base de prueba. Usa una cuenta de pruebas y revisa **Mis Tickets** después de cada flujo.

## Flujos que puedes probar

### 1. Capacidades y preguntas frecuentes

Inicia una conversación nueva para cada pregunta:

- `¿Qué funciones puedes realizar?`
- `¿Dónde están ubicados?`
- `¿Cuál es el horario de atención?`
- `¿Qué medios de pago aceptan?`
- `¿Cómo funciona el proceso de compra?`

**Comprueba:** el asistente explica capacidades y contesta con el contenido de `app/agents/jerarquico/knowledge_base/faq_servicio.md`. Estas consultas no deberían crear tickets ni cotizaciones. Los datos informativos son los que están escritos en ese Markdown.

### 2. Diagnóstico preliminar de hardware

Prueba, por ejemplo:

`Mi PC de escritorio se apaga cuando juego y se recalienta. Quiero revisarla.`

Si falta información, contesta las preguntas del agente en la misma conversación. Si ofrece un candidato de repuesto, comprueba que no lo presente como causa confirmada ni como compatible sin validar el modelo. Puedes decir `solo diagnóstico` si no quieres continuar con un repuesto.

**Comprueba:** clasificación como reparación, preguntas concretas si falta un dato, orientación provisional basada en el manual Markdown, creación del ticket cuando la solicitud queda clasificada y ausencia de un diagnóstico físico definitivo. El material de referencia está en `app/agents/jerarquico/knowledge_base/manual_servicio.md`.

### 3. Soporte de software

Prueba:

`Mi laptop con Windows 11 perdió el Wi-Fi después de una actualización.`

**Comprueba:** el flujo de soporte de software distingue hipótesis de hechos, evita pedir contraseñas o claves y no afirma haber reparado el equipo. Si la respuesta propone reinstalar o formatear, debe advertir sobre pérdida de datos y pedir autorización explícita.

### 4. Consulta y compra de un producto

Prueba:

`Quiero comprar una memoria RAM DDR4 de 16 GB.`

Si muestra alternativas, elige por número o nombre, por ejemplo `la primera`. Después revisa la propuesta y prueba `Sí, acepto` o, en otra conversación, `No, rechazo`.

**Comprueba:** precio y stock consultados en PostgreSQL, opciones cuando el nombre es ambiguo, cotización antes de aceptar y sin mostrar SKU al cliente. La aceptación registra la orden y el pago queda **PENDIENTE**; no se cobra ni se reserva inventario. El rechazo no debe crear el pago aceptado.

### 5. Venta de varios productos

Prueba:

`Quiero comprar una RAM de 8 GB y un SSD SATA de 240 GB.`

Resuelve las alternativas de cada artículo por separado, eligiendo por número o nombre cuando lo pida. Luego revisa la cotización.

**Comprueba:** se conserva la selección pendiente entre turnos y la propuesta incluye los artículos elegidos con precio y stock actuales. Si no existen productos que coincidan o no hay stock suficiente, el sistema debe informar que no puede cotizarlos.

### 6. Armado de PC

Prueba:

`Quiero armar una PC para juegos con presupuesto máximo de S/ 3,000.`

Elige uno de los perfiles disponibles por nombre o número. Si solicitas un cambio, por ejemplo `Cambia la RAM por una de 32 GB`, vuelve a elegir la alternativa de catálogo cuando se solicite y revisa la cotización recalculada antes de aceptarla.

**Comprueba:** pregunta por presupuesto o uso si faltan; presenta únicamente perfiles cuyos componentes existen activos en el catálogo con stock y precio; indica si el presupuesto no alcanza; los cambios sustituyen una pieza de la misma categoría y recalculan el total. La compatibilidad completa aún puede requerir validación del fabricante. Los perfiles están en `app/agents/jerarquico/knowledge_base/pc_build_profiles.md`.

### 7. Confirmación y rechazo de cotización

Al recibir una cotización, prueba en conversaciones separadas:

- Aceptar: `Sí, confirmo la cotización.`
- Rechazar: `No, rechazo la propuesta.`
- Respuesta ambigua: `Tal vez, primero quiero cambiar algo.`

**Comprueba:** solo la aceptación explícita guarda la cotización como aceptada y crea el pago pendiente; el rechazo cancela el ticket comercial asociado y no crea el pago; la respuesta ambigua debe pedir aclaración. Una cotización puede haber creado ya un ticket y un borrador antes de la decisión.

### 8. Preferencia logística

Después de aceptar una venta o armado, prueba:

- `Lo recojo en tienda.`
- En otra conversación: `Prefiero envío por courier.` Luego indica una empresa y dirección de entrega de prueba cuando las solicite.

**Comprueba:** queda registrada una preferencia logística. El courier necesita empresa y dirección. El registro no confirma pago, reserva, recepción, despacho, seguimiento ni entrega. En ventas y armados, al completar la preferencia se registra una garantía de 3 meses y se muestra su código.

### 9. Consulta de garantía

Con una póliza propia, prueba:

`¿Mi garantía WAR-… sigue vigente?`

Usa el código exacto de **Mis Tickets** o del comprobante. No pruebes con el código de otro cliente.

**Comprueba:** se muestra el estado y vencimiento guardados. Un código desconocido o que no pertenezca a la cuenta no revela información de otra persona.

### 10. Reclamo de garantía

Con una póliza propia vigente, prueba:

`Quiero registrar un reclamo por la garantía WAR-…; la pantalla parpadea.`

**Comprueba:** se registra un reclamo para revisión, no se promete cobertura ni reembolso y se solicita una preferencia de recepción del equipo. La resolución del reclamo requiere evaluación posterior.

### 11. Solicitud de reembolso pendiente

Este flujo exige un pago propio `COMPLETED`, no uno que siga `PENDING`. Primero escribe `Quiero un reembolso`; después envía en un solo mensaje el código, importe y motivo:

`PAY-ABC123; importe: S/ 25.50; motivo: producto defectuoso`

Reemplaza esos datos por referencias de prueba válidas de tu cuenta.

**Comprueba:** se registra una solicitud pendiente de revisión manual si el pago pertenece a la cuenta, está completado, no tiene una solicitud pendiente duplicada y el importe no excede el saldo reembolsable. El chat no devuelve dinero ni cambia el pago. Si no tienes un pago completado de prueba, este caso no se puede completar desde la interfaz por sí sola.

### 12. Compra a proveedor no disponible

Prueba:

`¿Pueden comprar al proveedor el repuesto que está agotado?`

**Comprueba:** se informa que no se puede confirmar proveedor, precio ni plazo; no se crea orden de compra ni se reserva inventario.

## Capacidades fuera del flujo automático

- El chat no cobra pagos ni confirma que se hayan recibido.
- No reserva ni descuenta stock al aceptar una cotización.
- No coordina ni rastrea despachos reales; solo guarda la preferencia logística.
- No compra a proveedores; esa ruta está implementada como no disponible.
- Los reembolsos quedan como solicitudes pendientes para resolución manual.
- El diagnóstico es preliminar; una persona técnica valida el equipo y la compatibilidad final.
- El reclamo de garantía queda en revisión; el grafo no decide automáticamente la cobertura final.

## Qué revisar en LangSmith y en el portal

- En LangSmith, verifica que la ejecución tenga `pattern_id=hierarchical` y que aparezcan los nodos apropiados: `customer_care_supervisor`, `faq_agent`, `knowledge_retrieval`, agentes técnicos, `warehouse_agent`, `sales_agent`, `billing_agent`, logística o garantía según el caso.
- En **Mis Tickets**, comprueba tickets y estados. Después de aceptar, el pago debe continuar pendiente. Después de logística, comprueba la preferencia y, para venta/armado, el código de garantía.
- No compares solo el texto de un nodo interno con el mensaje final del chat; observa la salida final del turno.
- Si una solicitud se clasifica por una ruta inesperada, guarda el mensaje usado, el patrón, los nodos recorridos y el resultado final. La clasificación depende del modelo y puede variar.

## Casos cubiertos por pruebas automatizadas

La guía refleja especialmente los flujos de `tests/integration/test_hierarchical_workflows.py`, `tests/integration/test_hierarchical_refund_flow.py`, `tests/integration/test_pattern_api.py` y los contratos de `tests/contract/patterns/`. La prueba manual con Groq y PostgreSQL utiliza servicios y datos reales de tu entorno, por eso puede producir alternativas distintas a los fixtures de prueba.
