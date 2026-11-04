# Especificación 09 — candidato de inventario para diagnóstico provisional

**Estado retrospectivo: Implementada según código y evidencia histórica; depende del catálogo disponible.**
**Evidencia revisada:** docs/12-candidato-inventario-diagnostico.md; app/agents/jerarquico/; app/database/repository.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Cuando la guía más relevante vincule de forma inequívoca un síntoma con un solo
artículo candidato, consultar disponibilidad y precio en el catálogo aunque la
causa todavía no esté confirmada.

## Comportamiento

1. El diagnóstico sigue siendo provisional y conserva la tarifa de diagnóstico.
2. El sistema toma el candidato de un único artículo del caso Markdown más
   relevante; no depende de que el LLM repita correctamente el código.
3. No afirma que el candidato resolverá el problema ni que es compatible con el
   modelo del cliente.
4. El agente de almacén consulta PostgreSQL. Solo precios y stock vigentes del
   catálogo forman parte de una propuesta.
5. Si la consulta encuentra varias opciones, las presenta con su código, precio y
   stock, sin seleccionar ninguna automáticamente. El ticket de diagnóstico ya
   creado se conserva.
6. La respuesta del cliente con un código ofrecido reanuda el estado pendiente,
   vuelve a consultar ese código y produce la propuesta habitual. La cotización
   requiere aceptación explícita en un turno posterior.
7. El cliente puede responder `solo diagnóstico` para continuar sin repuesto.
8. No se cotizan accesorios de la misma familia por una coincidencia parcial de
   nombre/código SSD.

## Criterios de aceptación

- El caso RAG de laptop lenta recupera `SSD_1TB` como candidato aun si el modelo
  devuelve `required_parts=[]` y `labor_task_type=diagnosis`.
- El precio y stock solo proceden de la consulta al catálogo.
- Varias opciones crean un estado de selección que persiste a través del turno;
  seleccionar un código sigue el flujo hasta una propuesta no guardada.
- Aceptar explícitamente la propuesta guarda el repuesto elegido; ninguna
  selección automática presume compatibilidad.
- Si no hay un caso pertinente o un candidato único, se conserva el diagnóstico
  sin repuestos.
