# 34. Dataset de evaluación LangSmith para el chat

Dataset de 15 consultas para comparar respuestas, uso de tokens, costo y latencia. Las entradas son consultas independientes y están formuladas para no confirmar escrituras, de modo que el experimento se pueda repetir sin alterar los datos.

## Qué compara

- Los casos `CUSTOMER` se envían a `/api/chat`. Ejecuta esos mismos casos en tres experimentos, cambiando solo `pattern`: `hierarchical`, `orchestrator` y `decentralized`.
- Los casos `ADMIN` se envían a `/api/admin/chat`. El chat ADMIN usa `AdminChatService` y capacidades compartidas; el selector `pattern` no ejecuta los tres grafos de cliente. Estos casos sirven para medir esa función, pero no para afirmar paridad o superioridad entre patrones.
- En el dataset, `role` y `fixture` son metadatos para el target de evaluación: no se envían como campos del contrato HTTP. El target usa `role` para escoger la sesión de prueba y la ruta, y sustituye los marcadores `{{...}}` por IDs reales de fixtures.

## Dataset

Cada `inputs.message` es una consulta para una conversación nueva. `outputs.checks` son criterios semánticos: evalúa el contenido y los efectos, no una frase literal.

```json
[
  {
    "id": "C01",
    "inputs": {"role": "CUSTOMER", "fixture": "faq_markdown", "message": "Hola, ¿dónde están ubicados y cuál es el horario habitual de atención?"},
    "outputs": {"intent": "faq_location_hours", "checks": ["Responde usando la ubicación y el horario documentados en el FAQ", "No crea tickets ni cotizaciones"]}
  },
  {
    "id": "C02",
    "inputs": {"role": "CUSTOMER", "fixture": "faq_markdown", "message": "¿Qué métodos de pago aceptan? ¿Me puedes confirmar el pago por este chat?"},
    "outputs": {"intent": "faq_payment_methods", "checks": ["Enumera solo los métodos documentados", "Aclara que el chat no confirma que un pago haya sido recibido", "No inventa cuentas, QR ni referencias"]}
  },
  {
    "id": "C03",
    "inputs": {"role": "CUSTOMER", "fixture": "faq_markdown", "message": "¿Qué cubre la garantía de un armado de PC y cómo pido que revisen una falla?"},
    "outputs": {"intent": "faq_warranty", "checks": ["Resume la política documentada", "Distingue solicitud de revisión de aprobación de cobertura", "No crea un reclamo"]}
  },
  {
    "id": "C04",
    "inputs": {"role": "CUSTOMER", "fixture": "faq_markdown", "message": "Mi laptop se calienta y se apaga. ¿Qué comprobaciones básicas y seguras puedo hacer antes de llevarla al taller?"},
    "outputs": {"intent": "technical_guidance", "checks": ["Da orientación segura respaldada por el RAG", "No presenta una causa como diagnóstico confirmado", "No crea un ticket sin autorización"]}
  },
  {
    "id": "C05",
    "inputs": {"role": "CUSTOMER", "fixture": "faq_markdown", "message": "¿Quién ganó la Copa Mundial de fútbol de 1950 y por qué?"},
    "outputs": {"intent": "out_of_scope", "checks": ["Declina o redirige amablemente al alcance de servicio, ventas y soporte", "No inventa una respuesta desde el RAG", "No realiza escrituras"]}
  },
  {
    "id": "C06",
    "inputs": {"role": "CUSTOMER", "fixture": "inventory_snapshot", "message": "Quiero comprar una memoria RAM de 8 GB. Busca opciones con stock y, si salen muchas, dime qué criterios puedo precisar."},
    "outputs": {"intent": "broad_inventory_search", "checks": ["Usa el catálogo y stock actuales", "Si el resultado es amplio, propone criterios observados en el catálogo, por ejemplo formato, generación o marca", "No mezcla una aclaración con filtros inventados"]}
  },
  {
    "id": "C07",
    "inputs": {"role": "CUSTOMER", "fixture": "inventory_snapshot", "message": "Busca una SSD SATA de 2.5 pulgadas Kingston de 480 GB. Indícame las coincidencias, su precio y stock actuales."},
    "outputs": {"intent": "specific_inventory_search", "checks": ["Los nombres, precios y existencias coinciden con la base de datos del fixture", "No completa atributos ausentes con suposiciones", "No crea una cotización"]}
  },
  {
    "id": "C08",
    "inputs": {"role": "CUSTOMER", "fixture": "inventory_snapshot", "message": "Busca una SSD SATA de 99 TB de la marca Inventada ZX-999. Si no existe, dime que no hay coincidencias y qué puedo cambiar."},
    "outputs": {"intent": "no_inventory_match", "checks": ["No inventa un producto ni stock", "Informa que no hay coincidencias y ofrece criterios alternativos", "No inicia compras a proveedores"]}
  },
  {
    "id": "C09",
    "inputs": {"role": "CUSTOMER", "fixture": "inventory_snapshot", "message": "Quiero cotizar una RAM de 8 GB y una SSD SATA de 480 GB. Primero busca opciones con stock; no elijas productos ni guardes o aceptes una cotización todavía."},
    "outputs": {"intent": "direct_sale_discovery", "checks": ["Busca cada familia de producto usando el inventario", "Pide criterios o elección si hay varias opciones", "No persiste cotización, reserva ni pago"]}
  },
  {
    "id": "C10",
    "inputs": {"role": "CUSTOMER", "fixture": "inventory_snapshot", "message": "Quiero cotizar una PC para trabajo de oficina con un presupuesto máximo de S/ 2,000. Antes de armar la propuesta, pregúntame lo que necesites y muéstrame opciones disponibles. No guardes ni aceptes nada todavía."},
    "outputs": {"intent": "pc_build_discovery", "checks": ["Aclara requisitos relevantes y consulta componentes del inventario", "No promete compatibilidad que no haya validado", "No crea cotización ni reserva stock"]}
  },
  {
    "id": "C11",
    "inputs": {"role": "CUSTOMER", "fixture": "customer_ticket_creation", "message": "Quiero que revisen mi laptop Lenovo ThinkPad E14: se apaga al iniciar Windows desde ayer. Quiero iniciar un caso de reparación, pero antes muéstrame el resumen y pide mi confirmación; no lo registres todavía."},
    "outputs": {"intent": "repair_ticket_proposal", "checks": ["Resume el equipo y el síntoma sin afirmar causa física", "Pide confirmación explícita", "No crea ticket antes de la confirmación"]}
  },
  {
    "id": "C12",
    "inputs": {"role": "CUSTOMER", "fixture": "customer_ticket_with_diagnosis", "message": "¿Cuál es el estado actual de mi ticket {{customer_ticket_code}} y qué diagnóstico preliminar figura?"},
    "outputs": {"intent": "own_ticket_status", "checks": ["Devuelve datos del ticket del CUSTOMER autenticado y coincidentes con el fixture", "Describe el diagnóstico como preliminar", "No revela registros de otro cliente"]}
  },
  {
    "id": "C13",
    "inputs": {"role": "CUSTOMER", "fixture": "customer_active_warranty", "message": "Consulta mi garantía {{customer_warranty_code}}. ¿Cuál es su estado y fecha de vencimiento?"},
    "outputs": {"intent": "own_warranty_lookup", "checks": ["Devuelve el estado y fecha que figuran en el fixture", "No garantiza que una futura falla esté cubierta", "No revela garantías ajenas ni crea un reclamo"]}
  },
  {
    "id": "A14",
    "inputs": {"role": "ADMIN", "fixture": "suppliers_snapshot", "message": "Muéstrame los proveedores activos con nombre, correo y teléfono registrados."},
    "outputs": {"intent": "admin_list_suppliers", "checks": ["Consulta datos reales y presenta filas estructuradas", "Respeta el filtro activo", "No devuelve JSON crudo como texto si existe presentación tabular"]}
  },
  {
    "id": "A15",
    "inputs": {"role": "ADMIN", "fixture": "accounting_snapshot", "message": "Lista los últimos cinco asientos contables confirmados con fecha, concepto, categoría, debe y haber."},
    "outputs": {"intent": "admin_list_accounting_entries", "checks": ["Consulta asientos existentes y presenta sus campos solicitados", "No altera ni revierte asientos", "No inventa registros cuando no hay resultados"]}
  }
]
```

## Cómo ejecutar el experimento

1. Usa una base de pruebas con un snapshot fijo de inventario y los fixtures indicados. Los casos C12 y C13 requieren sustituir los marcadores por códigos reales del CUSTOMER de prueba.
2. Crea un experimento para cada patrón cliente con el mismo conjunto C01–C13, el mismo CUSTOMER de prueba, la misma base y el mismo perfil de proveedor/modelo. El target convierte cada entrada a `POST /api/chat` con `pattern` del experimento, `message` de la fila y una conversación nueva.
3. Ejecuta A14–A15 como un experimento aparte contra `/api/admin/chat` con una sesión ADMIN de prueba. No incluyas sus métricas en la comparación de los tres grafos.
4. Guarda `scenario_id`, patrón, proveedor/modelo, tokens de entrada/salida, costo reportado por el proveedor, latencia y resultado del evaluador. Compara promedios y, si repites las corridas, también mediana y percentiles; identifica por separado el primer request frío del servicio.
5. Para comparar costo, LangSmith necesita que las trazas reciban el uso de tokens y metadatos de costo del proveedor. Si no aparecen, informa “no disponible”; no estimes costo a partir solo del texto.

## Controles de comparación y privacidad

- Las tres corridas de CUSTOMER deben recibir exactamente el mismo mensaje y estado inicial. Mantén constantes modelo, proveedor, temperatura, límites de tokens, documentos RAG y snapshot de BD. El número de llamadas al modelo propio de cada patrón sí forma parte del resultado.
- Usa una conversación aislada por ejemplo y no reutilices confirmaciones ni IDs de conversación entre experimentos.
- El set está pensado para consultas y propuestas sin confirmación. No agregues una respuesta “confirmo” a los casos: eso puede ejecutar operaciones. Prueba escrituras aceptadas en una suite funcional distinta, con base descartable y limpieza entre corridas.
- Usa solo cuentas y datos sintéticos. Con `LANGSMITH_HIDE_INPUTS=false` y `LANGSMITH_HIDE_OUTPUTS=false`, LangSmith guardará consultas y respuestas visibles; no incluyas nombres, correos, direcciones ni credenciales reales.
- Compara primero el resultado semántico y los efectos laterales. Una respuesta rápida que omite datos, viola permisos o inventa stock no es una mejora.

## Cobertura y límites

Los casos incluyen FAQ/RAG, abstención, soporte técnico, búsqueda y acotación de inventario, venta directa, armado PC, inicio seguro de ticket, consulta de ticket/diagnóstico, garantía y consultas administrativas de proveedores y contabilidad. No cubren el recorrido completo de aceptar cotizaciones, crear compras, confirmar pagos, solicitar reembolsos ni acciones administrativas de escritura; esos flujos requieren varias entradas, estado y revisión de sus efectos, por lo que deben probarse aparte y no repetirse como benchmark de solo lectura.
