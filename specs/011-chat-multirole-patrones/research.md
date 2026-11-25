# Research: Chat multirol coherente

## R1. Composición ASGI y recursos de patrones

**Decision**: `app/infrastructure/chat_app.py` será el único compositor efectivo; revisar `app/main.py` y retirar el bloque inalcanzable solo si se confirma que el ASGI publicado ya devuelve `build_chat_app()`.

**Rationale**: `create_app()` construye una app/lifespan, devuelve otra app creada por `build_chat_app()` y conserva un segundo bloque de composición después del `return`. Los recursos de la primera app no están asociados a la app publicada. La configuración real de los patrones se debe hacer en la fábrica que sí se exporta.

**Alternatives considered**: volver a una sola app con lifespan en `main.py`; usar una app montada. Preferir una raíz de composición reduce duplicación, siempre que los recursos requeridos por chat se gestionen en esa raíz.

## R2. Aislamiento de roles y confirmación ADMIN

**Decision**: endpoints CUSTOMER existentes continúan con `require_customer`; añadir endpoints ADMIN protegidos por `require_admin`, con caso de uso y registro de capacidades ADMIN diferentes. Conversaciones se particionan por rol y principal autenticado. Cada escritura debe crear una propuesta; el commit exige confirmación explícita del mismo ADMIN y conversación.

**Rationale**: `SendChatMessage` actualmente solo recibe `customer_id`; chat/audio actuales validan clientes. Las rutas ADMIN existentes ya están protegidas por `require_admin` y son la fuente de comportamiento. Una instrucción de prompt no puede ser el límite de autorización. El audio pasa por el mismo servicio de ejecución tras validar el principal.

**Alternatives considered**: compartir endpoint y dar herramientas al agente según rol; se rechaza porque facilita mezcla de identidad/conversación y permite errores de enrutamiento. Ejecutar escritura directamente tras intención del LLM; rechazado por la decisión explícita de confirmación.

**Proposal lifetime**: las propuestas viven dentro de la conversación en memoria existente. El usuario eligió descartarlas si Render reinicia o la confirmación llega a una instancia distinta; la API devuelve conflicto/ausencia de conversación y solicita repetir la operación. No se crea una tabla para propuestas.

## R3. Capacidades administrativas disponibles

**Decision**: primera versión solo expone lecturas/escrituras cubiertas por capacidades/repositorios API actuales: tickets, clientes, inventario, proveedores/compras y órdenes, cotizaciones de venta, catálogo/asientos contables. El agente informa cuando una acción no existe; no se inventa compra a proveedor ni se aprueba reembolso.

**Rationale**: las rutas existen en `chat_app.py`, pero no existe un agente ADMIN ni un mapa de funciones de herramienta que las consuma. Compras a proveedores y contabilidad requieren atribución ADMIN y sus validaciones actuales.

**Alternatives considered**: invocar rutas HTTP locales desde el agente; se rechaza porque crea llamadas en bucle, duplica auth/transporte y complica transacciones. Las capacidades deben ser puertos/casos de uso compartidos.

## R4. Fuentes RAG

**Decision**: declarar un manifiesto común con raíz de conocimiento aprobada en `app/agents/jerarquico/knowledge_base`; revisar cada Markdown de `data/knowledge` y `app/agents/orquestador/knowledge`, migrar contenido útil al corpus canónico sin perder su procedencia, y retirar fuentes duplicadas solo después de verificar usos.

**Rationale**: `app/rag/sources.py` agrega ahora tres raíces. Los agentes aplican filtros distintos y el recuperador técnico jerárquico también mantiene corpus construido por separado. Esto puede producir diferencias académicas y respuestas incompatibles.

**Alternatives considered**: conservar las tres raíces sin revisión; esto no satisface la fuente compartida. Copiar todo a ciegas; riesgo de arrastrar material conflictivo o de demostración.

## R5. Perfil efectivo de modelo

**Decision**: todos los constructores de agentes deben llamar al factory `create_model(settings)` o recibir un modelo inyectado; el perfil de traza se deriva de la misma instancia/configuración efectiva, no de valores declarativos independientes.

**Rationale**: el factory común ya existe, pero agentes descentralizados instancian `ChatGroq` con modelos hardcodeados; el test actual solo revisa metadata. La comparación de topologías pierde validez si el proveedor/modelo real varía.

**Alternatives considered**: cambiar solo la metadata; ocultaría, no corregiría, la diferencia real.

## R6. Cotización PC_BUILD independiente

**Decision**: registrar PC_BUILD como cotización comercial sin ticket; al aceptar, reservar los repuestos y mantener pago/pedido asociados a `quote_id`. La cotización de servicio REPAIR continúa ligada a ticket.

**Rationale**: el constraint SQL actual `chk_quotes_ticket_kind` permite `ticket_id IS NULL` solo para DIRECT_SALE. `app/agents/jerarquico/supervisor.py` crea ticket para todo tipo excepto SALE; `app/agents/jerarquico/sales.py` persiste solo SALE a través de la ruta de cotización directa. La migración 009 también asume que todo tipo distinto de DIRECT_SALE tiene ticket.

**Alternatives considered**: mantener ticket para PC_BUILD; contradice que tickets sean exclusivamente seguimiento de servicio. Crear otra tabla para armado; duplicaría ciclo existente de quote/reservation/payment/order sin necesidad demostrada.

**Migration risk**: `create_order_warranty` actualmente exige ticket para PC_BUILD, aunque el esquema de `warranties` ya admite `sales_order_id` y `ticket_id` nullable. El camino de pedido pagado valida hoy `quote_type='DIRECT_SALE'`. Puede ampliarse para `PC_BUILD` validando que cotización, pedido, cliente y pago correspondan; así se conserva la garantía sin ticket ficticio ni una nueva tabla. Los reclamos posteriores sí pueden originar un ticket de seguimiento.

## R7. Merge review

**Decision**: mantener compatibilidad mientras se resuelven duplicados; retirar definiciones redundantes únicamente después de mapear referencias y contratos.

**Findings**:
- `app/agents/decentralized/graph.py` define `build_graph` dos veces (aprox. líneas 660 y 683); la segunda definición oculta la primera. Debe consolidarse con la firma/configuración usada por `DecentralizedPattern` y tests.
- El adaptador `DecentralizedPattern` usa `MemorySaver` y no activa los flags/repositorios de escrituras, pese a que una definición más reciente del builder acepta esas dependencias. Revisar tests antes de elegir opciones predeterminadas.
- `app/main.py` tiene composición que queda después del `return` de la app efectiva; lifecycle/checkpointer local no corresponde a la app retornada.
- Los archivos `app/agents/decentralized/*` incluyen nombres/alias históricos referenciados por tests; conservarlos hasta comprobar importaciones.
- No se encontraron marcadores de conflicto Git al revisar el árbol actual; esto no demuestra que los bloques aceptados de ambos lados sean funcionales.

