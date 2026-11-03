# Evidencia 19 - precios y deduplicación del catálogo seed

Se revisó `contexto/inventario_multiagente_postgres_seguro.sql`. El catálogo pasó
de 438 a 310 filas. Se retiró la cuadrícula redundante de RAM por velocidades y
capacidades, conservando opciones por marca; se quitaron coincidencias exactas
entre ambos bloques para Kingston DDR4 8GB 3200, Crucial Ballistix 16GB DDR4
3200, Kingston NV2 500GB y WD Blue 1TB.

Se fijaron precios de referencia en PEN para RAM, almacenamiento y componentes de
PC. Referencias consultadas el 2026-10-13: Compuvision Perú publica Ryzen 5 5600
a S/425 y Kingston Fury Beast DDR4 16GB a S/145.77; Franktec Perú publica RAM
SODIMM DDR4 8GB a S/130 y 16GB a S/190, SSD NVMe 500GB a S/210 y 1TB a S/310,
y SSD SATA de 240GB a S/150. Los valores del seed siguen siendo demostrativos,
no una cotización en vivo.

Validación estática: 310 filas parseables, 310 códigos únicos, cero nombres y
categorías exactos repetidos; `git diff --check` correcto. No se ejecutó el SQL,
no se consultó ni modificó PostgreSQL. Limitación: las filas ya insertadas no
recibirán estos cambios al volver a ejecutar el script, porque ambos bloques usan
`ON CONFLICT (code) DO NOTHING`; actualizar la BD requiere una migración explícita.
