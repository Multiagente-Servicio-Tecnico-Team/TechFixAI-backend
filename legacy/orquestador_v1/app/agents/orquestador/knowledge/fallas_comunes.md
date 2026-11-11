# Catalogo tecnico y componentes en inventario

Los componentes siguientes corresponden a articulos activos consultados en
`spare_parts`. La cantidad y el precio nunca se toman de este archivo: el agente
de almacen los consulta en PostgreSQL en cada cotizacion. Validar modelo y
compatibilidad antes de incluir cualquier repuesto.

## Sobrecalentamiento y apagado repentino
- Sintomas: ventilador ruidoso, carcasa muy caliente, rendimiento reducido o apagados bajo carga.
- Causas probables: polvo en disipador, pasta termica degradada o ventilador desgastado.
- Diagnostico sugerido: verificar temperaturas, flujo de aire y giro del ventilador.
- Solucion: limpieza y renovacion de pasta termica; cambiar ventilador solo tras probarlo.
- Componente en inventario: `Pasta Térmica Arctic MX-4`.
- No hay ventiladores en el inventario actual; no solicitar un ventilador como repuesto cotizable.

## Laptop lenta o almacenamiento insuficiente
- Sintomas: inicio lento, pausas al abrir archivos o memoria insuficiente bajo carga.
- Causas probables: almacenamiento degradado/lleno o falta de memoria para la carga de trabajo.
- Diagnostico sugerido: revisar salud SMART, espacio libre y uso de memoria antes de cotizar hardware.
- Solucion: mantenimiento de software; ampliar RAM o migrar a SSD solo si las pruebas lo justifican.
- Componentes en inventario: `Memoria RAM DDR4 8GB` y `Disco SSD NVMe 512GB`.
- Validar DDR4, formato NVMe M.2, capacidad maxima y compatibilidad de la placa del modelo exacto.

## Equipo de escritorio no enciende
- Sintomas: no hay luces/arranque o se apaga al iniciar; confirmar que sea un equipo de escritorio.
- Causas probables: fuente de alimentacion, cableado, toma electrica o placa.
- Diagnostico sugerido: probar toma y cable, medir la fuente y aislar componentes antes de reemplazarla.
- Componente en inventario: `Fuente de Poder 500W 80+`.
- No ofrecer esta fuente para laptops ni sin verificar formato, conectores y consumo requerido.

## Bateria no carga o dura poco
- Sintomas: porcentaje detenido, descarga rapida o apagado al desconectar el cargador.
- Diagnostico sugerido: revisar salud/ciclos de bateria, cargador y conector antes de concluir que falla la bateria.
- Solucion: confirmar la falla con pruebas y explicar que el repuesto no esta disponible en inventario.
- No hay baterias ni cargadores en el inventario actual; no proponer otro componente como sustituto.

## Pantalla rota de iPhone 12
- Sintomas: vidrio/panel roto, lineas o ausencia de imagen en un iPhone 12.
- Diagnostico sugerido: confirmar que sea exactamente iPhone 12 y comprobar pantalla/tactil y conectores.
- Componente en inventario: `Pantalla iPhone 12`.
- No usar este repuesto para iPhone de otra generacion ni para pantallas de laptop.

## Pantalla de laptop sin imagen o con artefactos
- Sintomas: laptop enciende pero no muestra imagen, parpadea o presenta lineas.
- Diagnostico sugerido: probar monitor externo e inspeccionar cable eDP, panel y circuito grafico.
- Solucion: aislar la falla antes de cambiar componentes.
- No hay paneles LCD ni cables eDP de laptop en el inventario actual; no cotizar la pantalla de iPhone.

## Pantalla azul, reinicios o bloqueos
- Sintomas: errores de sistema, congelamientos o reinicios repetidos.
- Diagnostico sugerido: registrar codigo de error, probar memoria y revisar salud SMART.
- Componentes en inventario que podrian aplicar tras confirmar pruebas y modelo: `Memoria RAM DDR4 8GB` o `Disco SSD NVMe 512GB`.
- No atribuir la falla a una pieza sin evidencia ni proponer incompatibilidades.

## Wi-Fi intermitente o sin conexion
- Sintomas: redes ausentes, desconexiones o senal debil.
- Diagnostico sugerido: comparar redes/dispositivos, revisar controlador y antenas.
- El inventario actual no contiene tarjetas Wi-Fi ni antenas; no proponer un repuesto sin existencias.