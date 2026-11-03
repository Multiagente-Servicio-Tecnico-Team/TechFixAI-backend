# Spec 11 — Búsqueda comercial y armado de PC flexible

**Estado retrospectivo: Parcial — cubre perfiles curados y cambios; no arma configuraciones libres ni reserva stock.**
**Evidencia revisada:** docs/14-ventas-y-armado-pc-flexible.md; app/agents/jerarquico/
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Permitir que un cliente describa artículos, categorías y cambios con lenguaje
natural, obtenga configuraciones PC basadas en catálogo y complete el flujo
comercial sin conocer SKU ni códigos internos.

## Requisitos

1. **Búsqueda por nombre/categoría**
   - Recibir términos naturales y filtrar el catálogo activo con consultas SQL
     parametrizadas.
   - Mostrar solo opciones con stock positivo y precio positivo.
   - Si hay varias coincidencias, mostrar nombre, categoría, precio y stock con
     números de opción; aceptar selección por número o nombre.
   - Mantener los códigos solo en el estado interno y en las escrituras de BD.
   - En solicitudes con varios artículos, conservar la cola pendiente mientras
     el cliente resuelve cada selección.

2. **Armado según presupuesto y uso**
   - Pedir presupuesto máximo y uso principal si alguno no está especificado.
   - Recuperar perfiles curados desde Markdown local; consultar cada código
     interno exactamente en PostgreSQL para validar categoría, precio y stock.
   - Incluir el costo de mano de obra configurado en la comparación con el
     presupuesto; no cotizar cuando el perfil lo supera.
   - Calcular el precio total con `Decimal` y datos vigentes de PostgreSQL.
   - Informar las comprobaciones de compatibilidad todavía pendientes; no
     garantizar compatibilidad integral sin datos suficientes.
   - Mantener el uso que pidió el cliente. Si el perfil verificado supera el
     presupuesto, explicar el total y cuánto excede el tope; no cambiar a otro
     perfil de menor rendimiento sin que el cliente lo solicite.
   - Cuando haya varias configuraciones curadas del mismo uso que quepan en
     presupuesto, mostrarlas con diferencias claras y permitir elegir por
     número/nombre, o pedir la más económica/de mayor rendimiento.

3. **Modificación del armado**
   - Antes de aceptar la propuesta, permitir reemplazar RAM u otro componente
     disponible por categoría.
   - Presentar y seleccionar alternativas por número o nombre, sin SKU.
   - Volver a consultar inventario, conservar el resto de la configuración,
     sustituir el componente elegido y recalcular la cotización completa.
   - Solicitar una nueva aceptación explícita para la propuesta revisada.

4. **Cierre de ventas y armado**
   - Crear la cotización y el pago solo tras aceptación explícita; el pago queda
     `PENDING` y la preferencia logística `PENDING_RECEIPT`.
   - Tras registrar logística, generar idempotentemente la póliza de tres meses
     para ventas y armados aceptados, vinculada a cliente, ticket y cotización.
   - Despedirse con una respuesta final honesta: no afirmar pago recibido,
     reserva, recepción, ensamble o entrega mientras el esquema no lo confirme.

## Fuera de alcance / limitaciones

- No se agrega inventario de prueba ni script de carga: los perfiles se forman
  con filas existentes en la BD local.
- No se generan consultas SQL desde el LLM ni se usa un servidor MCP de SQL
  arbitrario.
- El armador disponible se limita a perfiles curados; todavía no genera
  combinaciones libres ni optimiza componentes para encajar automáticamente en
  cualquier presupuesto.
- La tabla de proveedores no aporta cotizaciones/plazos verificables.
- El catálogo no documenta todos los datos físicos de compatibilidad; las
  dimensiones/conectores de GPU, BIOS y revisión del fabricante pueden seguir
  pendientes.
- El pedido no reserva ni descuenta inventario.
- Las marcas están incluidas en el nombre/modelo del catálogo actual, por lo
  que no se requiere una columna `brand` para ofrecer variantes.

## Criterios de aceptación

- Una solicitud de RAM puede ofrecer y seleccionar variantes usando nombre o
  número sin exponer SKU.
- Un armado por presupuesto devuelve un perfil solo si las piezas existen,
  tienen stock/precio válidos y el total cabe en el presupuesto.
- Cambiar RAM reemplaza la categoría correspondiente y altera el total según el
  precio consultado; la cotización anterior no se acepta automáticamente.
- Después de aceptar y registrar logística de un armado o venta, existe una
  póliza asociada al mismo cliente/ticket/cotización y el flujo termina con
  despedida; el reintento no duplica la póliza.
- Las pruebas no escriben en la base local de demostración.
