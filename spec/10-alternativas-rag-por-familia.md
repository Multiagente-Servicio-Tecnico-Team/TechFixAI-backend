# Selección de alternativas de catálogo desde el RAG

**Estado retrospectivo: Implementada según evidencia histórica; la compatibilidad física no está modelada.**
**Evidencia revisada:** docs/13-alternativas-rag-por-familia.md; app/database/repository.py; app/agents/jerarquico/warehouse.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Generalizar a los casos del manual RAG el flujo de candidatos de inventario y
selección del cliente, sin asumir compatibilidad ni escoger un producto por él.

## Requisitos

1. Cuando el agente técnico elija un candidato del caso RAG, almacén consulta el
   código en PostgreSQL. Solo una coincidencia cuyo SKU sea exactamente el
   solicitado se considera directa; una coincidencia difusa no debe impedir
   consultar y presentar otras alternativas de la misma familia.
2. La búsqueda debe filtrar accesorios y categorías distintas aunque compartan
   fragmentos de texto con el nombre de la familia. Debe incluir categoría para
   filtrar y presentar artículos.
3. Cada opción presentada debe estar activa, tener precio positivo y stock
   suficiente; muestra código, descripción, precio unitario y stock obtenidos del
   catálogo.
4. Si hay varias opciones, no cotizar ni seleccionar automáticamente. Guardar
   temporalmente los códigos permitidos, esperar la selección del cliente y
   reconsultar el código elegido antes de cotizar.
5. Informar que una alternativa de inventario no prueba compatibilidad. La
   validación de modelo, formato e interfaz sigue a cargo del técnico.
6. Respetar alternativas «o» del manual y no cotizar productos de las distintas
   ramas a la vez. Si el agente no puede determinar una rama, continuar como
   diagnóstico o pedir aclaración.
7. Mantener dinero en `Decimal`; no inventar precios, existencias, proveedores ni
   plazos. Si no hay resultados cotizables, informar la limitación.

## Criterios de aceptación

- Caso de RAM recuperado del manual puede elegir el candidato `RAM_16GB` y mostrar
  opciones de marcas/modelos presentes en las categorías RAM Desktop y RAM Laptop.
- Productos de Herramientas como `TOOL-ESD` no aparecen entre opciones de RAM.
- Una búsqueda difusa única de `Ventilador_CPU` no preselecciona un ventilador si
  el catálogo ofrece más variantes; gabinetes con ventiladores incluidos quedan
  excluidos.
- Seleccionar un código permitido consulta de nuevo el catálogo y continúa a la
  confirmación de cotización.
- Los casos SSD y otras familias mantienen su selección multi-turno.
- Una misma coincidencia textual en categoría vecina no cuenta como producto de
  la familia solicitada.

## Evidencia y limitaciones

- La tabla local `spare_parts` incluye `category` y, para RAM, las categorías
  `RAM Desktop` y `RAM Laptop`. La búsqueda de prueba devolvió diez opciones
  distintas sin incluir `TOOL-ESD`.
- El esquema del catálogo no expresa compatibilidad por fabricante/modelo, socket,
  generación DDR ni interfaz. Las opciones se presentan para revisión, no como
  compatibles.
- La selección y cotización se validan con repositorios de prueba; no se hacen
  escrituras a PostgreSQL.
- Checkpoint de commit del usuario: ____________________.
