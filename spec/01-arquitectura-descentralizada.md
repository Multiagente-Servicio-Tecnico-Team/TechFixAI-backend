# Arquitectura de red descentralizada

**Estado retrospectivo: Histórica / parcial — describe la rama aislada; confirmar diferencias con develop.**
**Evidencia revisada:** app/agents/decentralized/; features.md; esta especificación
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo y alcance

El módulo atiende consultas de soporte, diagnóstico técnico, disponibilidad de repuestos y cotización mediante cuatro agentes implementados en Python y LangGraph. Esta descripción corresponde al código de la rama `patron-red-rag-aislado`. La integración con el frontend del equipo todavía debe verificarse.

## Patrón arquitectónico

Los agentes tienen responsabilidades diferenciadas y transfieren el control mediante herramientas de handoff. No existe un agente supervisor que decida todas las intervenciones. Soporte recibe la primera consulta; los siguientes turnos pueden comenzar en el agente activo.

La arquitectura representa una red dirigida parcialmente conectada. Los agentes comparten estado y se ejecutan dentro del mismo grafo y proceso; no son servicios independientes ni se ejecutan todos en paralelo. Un handoff cambia el agente que atiende, pero no intercambia sus roles.

LangGraph centraliza la ejecución y las validaciones técnicas de las rutas. La descentralización corresponde a la colaboración entre agentes, no a un despliegue distribuido.

## Vista conceptual

Las flechas entre agentes representan transferencias permitidas, no una secuencia obligatoria. Los nodos internos de herramientas y auditoría se omiten para facilitar la lectura.

![Arquitectura de red descentralizada](./arquitectura%20descentralizada.png)

El estado compartido no es una etapa posterior a los agentes: cada nodo lo consulta y devuelve actualizaciones durante la ejecución. El resultado final incluye ese estado actualizado.

## Responsabilidades y componentes

| Componente | Responsabilidad | Archivo |
|---|---|---|
| Soporte | Consultas generales, herramienta de tickets y derivación inicial | `app/agents/decentralized/soporte.py` |
| Técnico | Orientación diagnóstica, preguntas de compatibilidad y derivación de consultas comerciales | `app/agents/decentralized/tecnico.py` |
| Almacén | Consulta de repuestos identificados y envío de resultados a Ventas | `app/agents/decentralized/almacen.py` |
| Ventas | Información comercial y cotización preliminar con inventario validado | `app/agents/decentralized/ventas.py` |
| Grafo | Nodos, herramientas, rutas, auditoría y límites | `app/agents/decentralized/graph.py` |
| Estado | Contrato de datos compartidos | `app/agents/decentralized/state.py` |
| Conversación | Historial y agente activo entre turnos, aislamiento por instancia | `app/agents/decentralized/conversation.py` |
| Políticas | Reglas explícitas de intención, identificación y presentación comercial | `app/agents/decentralized/policy.py` |
| Repositorio | Acceso y búsqueda de inventario | `app/database/repository.py` |

## Flujo de ejecución

1. El consumidor conserva una instancia de `Conversation` por conversación y llama a `send()` por mensaje.
2. `route_entry()` selecciona el agente activo válido o Soporte como entrada inicial.
3. El nodo aplica reglas locales y, cuando corresponde, consulta el modelo Groq.
4. Las llamadas a herramientas se ejecutan mediante `ToolNode`.
5. Los nodos de auditoría validan transferencias y actualizan contadores e historial. Los resultados de Almacén pasan por `guardar_inventario()`.
6. Las rutas condicionales continúan en el agente seleccionado o finalizan el turno.
7. `Conversation` conserva el resultado exitoso para el siguiente mensaje. `new_request=True` descarta el contexto anterior.

Las rutas pueden ser solicitadas por el modelo o por reglas deterministas. Una solicitud de cotización con repuestos puede requerir pasar primero por Almacén; el grafo valida el alcance y la identificación antes de permitirla.

## Estado y controles

`AgentState` contiene mensajes, agente actual y siguiente, historial y contador de handoffs, iteraciones de herramientas, repuestos requeridos, resultados de inventario, alcance de cotización y errores. `turn_start_index` permite distinguir las herramientas del turno actual.

El historial de mensajes usa el reductor `add_messages`. `Conversation` y la API autenticada reinician los controles por turno y conservan el contexto de negocio. En API, `turn_start_index` se calcula desde los mensajes del checkpoint del `thread_id`, para que las herramientas previas no se confundan con las del turno actual. El grafo establece límites de cinco transferencias y seis iteraciones de herramientas por agente.

Las cotizaciones utilizan `Decimal` y moneda PEN. No se confirma mano de obra sin tarifa verificada; disponibilidad no implica compatibilidad, reserva ni compra. La identificación de repuestos evita aceptar automáticamente un componente inventado por el modelo.

## Integración RAG

Los documentos Markdown de `data/knowledge/` se cargan mediante `cargar_documentos()` y se fragmentan con `dividir_documentos()` en `app/rag/ingest.py`. La ingesta utiliza FastEmbed y persiste los vectores en Chroma.

`buscar_conocimiento()` en `app/rag/retriever.py` realiza búsquedas semánticas. Soporte, Técnico y Ventas disponen de la herramienta `consultar_base_conocimiento`, que devuelve fragmentos con su fuente. Almacén consulta inventario mediante sus herramientas.

La existencia de este flujo no garantiza la fundamentación de cada respuesta. Queda pendiente evaluar relevancia, fidelidad documental y cobertura del conocimiento. La recuperación actual no aplica filtro por área ni umbral de relevancia; la configuración de ingesta y recuperación está duplicada.

La instalación raíz incluye `requirements-agent.txt`, que declara las dependencias del RAG. Tras instalarlas, se debe ejecutar `python -m app.rag.ingest` para generar el índice local `data/chroma/`; no se crea automáticamente al iniciar la API.

## Evidencia de validación

Se observó manualmente el recorrido `Soporte → Ventas → Almacén → Ventas → Técnico`, conservando el contexto del SSD. También se verificó que corregir una referencia de 5000GB a 500GB provoca una nueva consulta, sin sustituir automáticamente el producto.

La última ejecución de la selección de pruebas unitarias registró **89 casos aprobados y cero fallidos**, distribuidos en siete archivos. Las pruebas de conversación simulada, repositorio con SQLite y RAG se clasifican por separado. Este resultado no valida el frontend ni todos los escenarios del sistema.

`tests/test_e2e_decentralized.py` invoca directamente el grafo; no representa todavía un E2E de navegador, API y agentes. Algunos imports de la selección unitaria activan intentos de conexión a LangSmith: falta completar su aislamiento. Los scripts `test_email.py` y `test_database.py` realizan operaciones reales al importarse y no deben incluirse indiscriminadamente en una ejecución aislada.

## Limitaciones y siguientes pasos

- Integrar el backend y frontend conservando una conversación por sesión; verificar aislamiento entre usuarios.
- La conversación vive en memoria: reiniciar el proceso pierde el contexto. No proporciona autenticación ni almacenamiento durable.
- Implementar listado de catálogo; el flujo actual solicita una referencia concreta y su extracción conversacional está centrada en SSD.
- Incorporar documentación suficiente para confirmar compatibilidad y tarifas oficiales de servicios.
- No hay reserva de citas ni confirmación de contacto en el flujo descrito.
- Ampliar pruebas con paráfrasis, errores de servicios y casos de varios repuestos.
- Evaluar RAG con métricas de recuperación y fundamentación.
- ISO, Lighthouse y comparación académica entre patrones requieren evidencia independiente; no se consideran cumplidos por este documento.
