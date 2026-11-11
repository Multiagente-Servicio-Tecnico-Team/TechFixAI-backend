# Fuente del catálogo PCGE

`pcge_modificado_2019.csv` contiene 1192 códigos y denominaciones extraídos del PCGE Modificado 2019 publicado por el Ministerio de Economía y Finanzas del Perú: <https://www.mef.gob.pe/contenidos/conta_publ/documentac/PCGE_2019.pdf>. `source_line` permite localizar la entrada en el PDF.

`account_group`, `normal_balance` e `is_postable` son una clasificación operativa inferida para la carga inicial; no forman parte de una certificación MEF. Debe revisarla un contador antes del uso real. Los códigos 89, 891 y 892 quedan sin naturaleza normal y no imputables. No se vincularon automáticamente líneas de asientos históricos a estas cuentas.

Verificación estática: 1192 filas, 1192 códigos únicos, todos los padres presentes, nombres dentro del límite de 200 caracteres, ninguna cuenta imputable sin saldo normal y ninguna cuenta imputable con hijos.
