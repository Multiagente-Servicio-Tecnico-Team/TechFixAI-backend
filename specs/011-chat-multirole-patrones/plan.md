# Implementation Plan: Chat multirol coherente para los tres patrones

**Branch**: `011-chat-multirole-patrones` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

## Summary

Conservar los grafos jerárquico, orquestador y descentralizado, pero normalizar las capacidades disponibles, las reglas por rol, el corpus RAG y el perfil efectivo del modelo. Añadir chat y audio autenticados para ADMIN con una conversación aislada de la experiencia del cliente y un ciclo de propuesta/confirmación para toda escritura. Adaptar la venta PC_BUILD a una cotización independiente sin ticket, con reservas, pagos y pedidos relacionados a la cotización.

## Technical Context

**Language/Version**: Python 3.11+ (runtime actual del backend)
**Primary Dependencies**: FastAPI, LangGraph, LangChain/Groq, SQLAlchemy, PostgreSQL
**Storage**: PostgreSQL; registro de conversaciones/checkpoints actual en memoria
**Testing**: pytest; pruebas de contrato existentes en `tests/contract/patterns`
**Target Platform**: API ASGI local/Render
**Project Type**: Backend web API
**Performance Goals**: Reutilizar límites actuales de chat/audio; no introducir latencia externa adicional excepto transcripción y LLM
**Constraints**: conservar topologías; la autorización no puede depender del LLM; las escrituras ADMIN siempre requieren confirmación; no exponer datos de cliente a herramientas ADMIN sin alcance autorizado; no ejecutar scripts de reconstrucción
**Scale/Scope**: tres patrones, dos roles funcionales (CUSTOMER/ADMIN), chat de texto/audio, capacidades ya presentes en rutas ADMIN

## Constitution Check

- **Reglas compartidas**: las capacidades, permisos, validación, contratos de error y datos operativos serán compartidos; los tres grafos conservan sus topologías. PASS.
- **Persistencia autorizada**: la identidad se obtiene de la sesión; el LLM solo interpreta/proponen; toda escritura ADMIN exige confirmar. PASS con diseño de propuesta vinculada a actor y conversación.
- **Exactitud financiera**: persistir cotizaciones desde catálogo/tarifas y revalidar precios, stock y estado en la confirmación. PASS.
- **Evidencia**: RAG de documentos comunes, datos transaccionales desde PostgreSQL, abstención ante falta de evidencia. PASS.
- **Seguridad**: rutas y capacidades de rol ADMIN separadas; conversaciones aisladas; trazas minimizadas. PASS.
- **Cambios de esquema**: migración versionada para la regla de ticket de cotización; ningún SQL de reconstrucción se ejecuta. PASS.
- **Pruebas comparables**: contrato común invocado sobre los tres adaptadores. PASS.
- **Restricciones de la constitución**: no se automatiza compra a proveedor; no se procesa reembolso; checkpoints durables multiinstancia quedan fuera. PASS.

## Design Decisions

1. Mantener un punto de composición único (`build_chat_app`) y eliminar la composición inalcanzable/duplicada de `app/main.py` tras comprobar que el ASGI exportado no depende de ella.
2. Añadir casos de uso de chat ADMIN separados de `SendChatMessage` del cliente. La capa de aplicación administra conversación y propuesta temporal en memoria; adaptadores de capacidades ejecutan operaciones de los repositorios existentes.
3. No permitir que una llamada de herramienta escriba directamente. El primer turno crea una propuesta validada y resumida; una respuesta de confirmación explícita, bajo el mismo actor/conversación, ejecuta el comando. Confirmar revalida y es idempotente. Si la conversación no está disponible tras reinicio o en otra instancia, se rechaza y se vuelve a proponer; no se añade persistencia PostgreSQL para propuestas pendientes.
4. Compartir registro tipado de herramientas/políticas por rol y contexto de invocación. Cada patrón conserva su topología y adapta la selección/enrutamiento al mismo contrato.
5. Usar `app/agents/jerarquico/knowledge_base` como corpus documental canónico solicitado; reconciliar y mover documentos útiles de `data/knowledge` y `app/agents/orquestador/knowledge`, conservando procedencia estable. Excluir documentos que contradigan evidencia operativa y mantener PostgreSQL como fuente transaccional.
6. Construir todos los modelos mediante `app/adapters/llm/model_factory.py`; pasar `Settings` a los patrones que hoy crean Groq directamente. El perfil incluirá proveedor, modelo y parámetros efectivos usados en cada llamada.
7. Para PC_BUILD, reutilizar persistencia de cotización de venta, reserva, pago y pedido, preservando metadata de armado en observaciones/líneas según contratos existentes. Una migración sustituye `chk_quotes_ticket_kind`: DIRECT_SALE y PC_BUILD requieren `ticket_id IS NULL`; REPAIR requiere ticket. La garantía postventa se vincula al pedido pagado usando el campo `sales_order_id` que ya existe; un reclamo posterior puede abrir un ticket de seguimiento.
8. La composición de chat ADMIN no abre APIs genéricas nuevas para las capacidades no disponibles. Cada herramienta delega al repositorio/aplicación existente y preserva su validación y autoría.

## Project Structure

```text
app/
├── application/                 # Casos de uso, políticas compartidas y contratos
├── adapters/api/                # Rutas chat cliente y admin
├── adapters/patterns/           # Adaptadores de los tres grafos
├── adapters/llm/                # Perfil efectivo y trazabilidad
├── adapters/persistence/        # Adaptadores de capacidades operativas existentes
├── infrastructure/chat_app.py   # Composición única de la API
├── rag/                         # Fuentes, ingestión, recuperación y procedencia común
└── agents/                      # Topologías y prompts de cada patrón
sql/migrations/                  # Migración aditiva de cotización PC_BUILD sin ticket
tests/contract/patterns/          # Contratos comunes para los tres patrones
specs/011-chat-multirole-patrones/
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Nuevo flujo conversacional ADMIN y protocolo de confirmación | El chat/voz debe operar recursos administrativos con autorización y atribución verificable | Reusar el grafo de cliente podría exponer datos y ejecutar acciones sin confirmación; añadir solo un prompt no es un control de autorización |
| Migración SQL para PC_BUILD sin ticket | El constraint vigente prohíbe cotizaciones PC_BUILD independientes | Mantener ticket ficticio contradice la decisión de negocio y mezcla servicio técnico con venta |

