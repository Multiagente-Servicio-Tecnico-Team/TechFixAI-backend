# Evidencia 12 — candidato de inventario durante diagnóstico

## Causa

El manual ya contenía los casos 5 y 10 relacionados con lentitud y recomendaba
`SSD_1TB`, pero el prompt de soporte decía que cualquier `diagnosis` debía
devolver cero repuestos. Luego el agente técnico descartaba todas las piezas en
la rama `labor_task_type == "diagnosis"`. Por ello no se consultaba la BD y la
respuesta solo mostraba S/ 50.00 de diagnóstico.

## Cambios

- El caso 10 documenta un SSD como candidato provisional para buscar en el
  catálogo; la necesidad y compatibilidad requieren validación técnica.
- Si el caso más relevante tiene un único artículo, el agente técnico lo envía
  al agente de almacén incluso cuando el trabajo sigue siendo `diagnosis`.
- Los artículos, precios y stock siempre se obtienen de PostgreSQL. Varias
  opciones se presentan sin elección automática; para SSD se excluyen
  coincidencias cuyo código y nombre no sean de unidades SSD.
- Se conserva el estado de selección entre turnos. El cliente puede responder
  con uno de los códigos listados o `solo diagnóstico`; elegir un código conduce
  a la cotización habitual, que sigue necesitando confirmación.
- Se corrigió el texto cuando no hay stock: ya no afirma que no se guardó el
  ticket, pues este se crea durante el triage.

## Validación

- El recuperador local para el mensaje reportado devuelve primero el caso 10 y
  después el caso 5, ambos con `SSD_1TB`.
- PostgreSQL local: cero coincidencias exactas para `SSD_1TB`; hay múltiples
  unidades SSD activas con precio y stock, por lo que no se elige una
  automáticamente. La búsqueda también devolvía una carcasa USB por coincidencia
  parcial; ahora se excluye de las opciones SSD.
- Ejecución real con Groq y lecturas de inventario: resultado
  `awaiting_inventory_selection`; el ticket y las escrituras se sustituyeron por
  dobles de prueba, así que no se escribieron filas en PostgreSQL.
- La suite jerárquica enfocada y pruebas del estado multi-turno pasan.
- Checkpoint de commit del usuario: ____________________.
