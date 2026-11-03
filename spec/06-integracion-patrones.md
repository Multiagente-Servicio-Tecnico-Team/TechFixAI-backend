# Spec 06 — integración de patrones LangGraph en el portal

**Estado retrospectivo: Parcial — integración común implementada; las capacidades varían por patrón.**
**Evidencia revisada:** app/adapters/patterns/; app/main.py; features.md; docs/06-integracion-patrones.md
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Conectar el portal React autenticado con los patrones Jerárquico, Orquestador y
Red Descentralizada mediante un único contrato de chat, permitir seleccionar el
patrón antes de conversar y asociar la ejecución con trazabilidad de LangSmith.

## Requisitos

- **REQ-06-01 — Selector por conversación:** el cliente puede seleccionar uno de
  los tres patrones antes del primer mensaje. El patrón se conserva en toda la
  conversación; para cambiarlo debe iniciar una conversación nueva.
- **REQ-06-02 — API autenticada:** `GET /api/chat/patterns` y `POST /api/chat`
  requieren la cookie de sesión y obtienen la identidad del cliente de
  `SessionGuard`, nunca del cuerpo enviado por el navegador.
- **REQ-06-03 — Contrato común:** mensajes, acciones de guardar/rechazar propuesta,
  presupuesto y ticket se normalizan al contrato de `app/chat/contract.py`.
- **REQ-06-04 — Estado por conversación:** el ID de conversación es el
  `thread_id` de LangGraph. Un ID pertenece al cliente que lo inició y queda
  ligado al patrón que eligió.
- **REQ-06-05 — Trazabilidad:** las invocaciones se etiquetan con el patrón y
  ocultan entradas y salidas en LangSmith. Los metadatos explícitos no incluyen
  email ni texto del cliente; los detalles de error se redactan.
- **REQ-06-06 — UX y capacidades honestas:** el selector se bloquea durante una
  conversación, permite iniciar otra y explica que la Red Descentralizada usa
  herramientas simuladas y no persiste tickets/presupuestos.
- **REQ-06-07 — Dependencias reproducibles:** los requisitos raíz instalan el
  stack de autenticación y agentes y declaran las dependencias directas usadas
  por los tres patrones y sus interfaces.

## Fuera de alcance

- Migrar la Red Descentralizada a inventario o persistencia real.
- Unificar internamente los repositorios de datos de Jerárquico y Orquestador.
- Validar credenciales reales, desplegar servicios o modificar el esquema
  PostgreSQL.
- Cambiar de versión mayor React Router.

## Criterios de aceptación

1. Un visitante sin sesión recibe `401`; un cliente autenticado solo accede a sus
   conversaciones.
2. El backend ejecuta únicamente el patrón solicitado, rechaza cambios de patrón
   en una conversación existente y asigna `thread_id` igual al ID de conversación.
3. La UI envía `pattern`, bloquea su edición después del primer mensaje y permite
   volver a seleccionar al comenzar otra conversación.
4. LangSmith se puede desactivar; cuando se activa, el cliente configura
   ocultamiento de entradas/salidas y los tags identifican el patrón sin incluir
   el contenido del mensaje.
5. Los tres patrones producen la forma común de respuesta; los patrones con
   persistencia informan el presupuesto/ticket según su estado real.
6. Las pruebas aisladas de backend y frontend, y el build del frontend, pasan.
