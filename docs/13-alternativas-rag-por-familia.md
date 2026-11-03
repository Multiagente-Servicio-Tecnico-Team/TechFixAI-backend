# Evidencia: alternativas de inventario para los casos RAG

## Cambio

- `manual_servicio.md` ahora define reglas comunes para todos los casos: lookup del
  código, búsqueda acotada por familia, filtro de accesorios, lista de opciones
  activas con precio y stock, selección explícita y validación técnica posterior.
- El caso de RAM casi llena orienta al técnico a consultar marcas/capacidades RAM
  solo cuando el síntoma respalda una ampliación. El manual conserva la distinción
  entre alternativas «o» y varios componentes «y».
- En diagnóstico provisional, soporte puede seleccionar un único candidato de
  entre las alternativas del manual cuando los síntomas respaldan esa elección.
  Si no puede elegir, no se consultan ni cotizan las familias mezcladas.
- El repositorio incluye categoría en las alternativas y filtra familias conocidas
  (RAM, SSD, fuente, pasta térmica, ventilador, batería, pila CMOS y servicios).
  El filtro de batería excluye pilas RTC/CMOS y el de ventilador no acepta
  gabinetes solo porque incluyan ventiladores. Almacén vuelve a aplicar un filtro
  de familia antes de presentar opciones.
- Solo un SKU exactamente igual al código solicitado se trata como coincidencia
  directa. Una coincidencia difusa única (observada con `Ventilador_CPU`) no oculta
  las otras opciones cotizables de la familia.
- La selección multi-turno conserva los códigos permitidos; el código del cliente
  vuelve a consultarse antes de preparar el presupuesto.

## Pruebas y validación

- Prueba de regresión: RAM con dos opciones de memoria y un kit de herramientas
  impostor; solo se muestran las dos memorias y se continúa al seleccionar un SKU.
- Prueba de repositorio: la consulta de alternativas de RAM restringe categorías y
  nombres, evitando usar la subcadena `RAM` en `Herramientas`.
- Lectura real de la BD local de prueba: `find_spare_part_alternatives("RAM_16GB")`
  devuelve diez artículos RAM entre Desktop/Laptop de varias marcas, sin `TOOL-ESD`.
- El catálogo de prueba no ofrece batería de laptop entre las alternativas de
  `REP-BAT-L2023`; la única coincidencia por subcadena era una batería RTC/CMOS y
  ahora se excluye en lugar de sugerirse erróneamente.
- La BD contiene distintas generaciones, formatos y capacidades RAM; el código no
  tiene metadatos de compatibilidad. El flujo avisa al cliente que el técnico debe
  verificar el modelo y no afirma que todas las opciones sirvan para su equipo.
- No se alteraron tickets, cotizaciones ni existencias reales.

## Estado

- Pruebas enfocadas (`test_multiagent_graph.py`, `test_repository.py`): 49/49
  aprobadas. Pylance sin errores en todos los archivos Python afectados.
- `git diff --check` se ejecuta como verificación final.
- Checkpoint de commit del usuario: ____________________.
