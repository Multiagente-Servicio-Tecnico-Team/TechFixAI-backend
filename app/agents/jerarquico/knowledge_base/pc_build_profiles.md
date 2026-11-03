# Perfiles de armado de PC

Perfiles iniciales de referencia para la base de datos ficticia de demostración.
Los códigos se usan internamente para consultar stock y precio actuales; nunca
se muestran al cliente. El almacén debe rechazar el perfil si falta un artículo,
no tiene precio positivo o no hay stock suficiente. Los importes se calculan con
los precios vigentes del catálogo y `Decimal`; este documento no define precios.

## oficina-estudio

**Nombre**: PC para oficina y estudio
**Uso**: oficina, estudio, navegación, trabajo
**Compatibilidad**: CPU AM4 con gráficos integrados y placa AM4 DDR4 ATX; memoria DDR4 UDIMM de escritorio; disipador declarado compatible con AM4; gabinete ATX. La placa declara M.2 NVMe. Verificar BIOS, kit de montaje, conectores y compatibilidad final con las fichas del fabricante antes del ensamble.

- Procesador: `CPU-AMD-R5-5600G`
- Placa Madre: `MB-ASUS-B550-PLUS`
- RAM Desktop: `RAM-D-DDR4-3200-16-CRU`
- Almacenamiento: `SSD-M2-NVME-1TB`
- Refrigeración PC: `COOL-AIR-AG400-BK`
- Fuente de Poder: `PSU-COOLERMASTER-650-Gold`
- Gabinete: `CASE-COR-4000D-AIR`

## gaming-inicial

**Nombre**: PC de entrada para juegos
**Uso**: juegos, videojuegos, gaming, gamer
**Compatibilidad**: CPU y placa AM4 DDR4; RAM DDR4 de escritorio; disipador declarado compatible con AM4; GPU PCIe x16; fuente de 650 W y gabinete ATX. La GPU requiere revisar dimensiones, conectores y consumo frente a la ficha del fabricante. El PCIe puede depender de la CPU. No presentar como compatibilidad integral garantizada sin esa revisión.

- Procesador: `CPU-AMD-R5-5600`
- Placa Madre: `MB-ASUS-B550-PLUS`
- RAM Desktop: `RAM-D4-32GB-3600-COR`
- Tarjeta de Video: `GPU-ASUS-RTX3050-8G`
- Almacenamiento: `SSD-M2-NVME-1TB`
- Refrigeración PC: `COOL-AIR-AG400-BK`
- Fuente de Poder: `PSU-COOLERMASTER-650-Gold`
- Gabinete: `CASE-COR-4000D-AIR`

## gaming-economico

**Nombre**: PC gamer económica
**Uso**: juegos, videojuegos, gaming, gamer
**Compatibilidad**: CPU AM4 con GPU dedicada y placa B550 AM4 DDR4; RAM DDR4 de escritorio; SSD M.2 NVMe y disipador indicado para AM4. La GPU PCIe no requiere conector de energía externo según el catálogo. Verificar BIOS, dimensiones, conectores y compatibilidad final con fichas del fabricante.

- Procesador: `CPU-AMD-R5-5600`
- Placa Madre: `MB-ASUS-B550-PLUS`
- RAM Desktop: `RAM-D-DDR4-3200-16-CRU`
- Tarjeta de Video: `GPU-MSI-GTX1650-4G`
- Almacenamiento: `SSD-NVME-KINGSTON-NV2-500`
- Refrigeración PC: `COOL-AIR-AG400-BK`
- Fuente de Poder: `PSU-COOLERMASTER-650-Gold`
- Gabinete: `CASE-MSI-FORGE-100R`

## gaming-rendimiento

**Nombre**: PC gamer de mayor rendimiento
**Uso**: juegos, videojuegos, gaming, gamer
**Compatibilidad**: CPU Ryzen AM4 y placa B550 DDR4; RAM DDR4 de escritorio; SSD M.2 NVMe. GPU PCIe con 12GB; fuente de 750W. Verificar BIOS, dimensiones, conector y consumo de GPU, refrigeración y compatibilidad final con fichas del fabricante.

- Procesador: `CPU-AMD-R5-5600X`
- Placa Madre: `MB-ASUS-B550-PLUS`
- RAM Desktop: `RAM-D-DDR4-3600-32-CVL`
- Tarjeta de Video: `GPU-GIGA-RTX3060-12G`
- Almacenamiento: `SSD-NVME-KINGSTON-NV2-1000`
- Refrigeración PC: `COOL-AIR-AG400-BK`
- Fuente de Poder: `PSU-CORSAIR-750-Gold`
- Gabinete: `CASE-COR-4000D-AIR`

## Reglas para adaptar un armado

- Preguntar el presupuesto máximo y el uso si no aparecen en la solicitud.
- Cotizar solo componentes encontrados activos, con stock suficiente y precio
  positivo en PostgreSQL.
- Cuando el cliente pida más RAM, otro almacenamiento u otro componente, buscar
  opciones de la misma categoría en el inventario y pedir que elija por nombre o
  número. No pedir ni revelar SKU/códigos.
- Aplicar el cambio a la configuración conservada, volver a verificar el
  inventario y recalcular todos los importes antes de pedir aceptación.
- No afirmar compatibilidad completa basándose solo en este perfil; comunicar
  las verificaciones pendientes descritas arriba.
