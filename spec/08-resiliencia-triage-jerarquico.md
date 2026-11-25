# Especificación 08 — resiliencia del triage jerárquico

**Estado retrospectivo: Implementada según evidencia histórica; no se reejecutaron pruebas en esta revisión.**
**Evidencia revisada:** docs/11-resiliencia-triage-jerarquico.md; app/agents/jerarquico/supervisor.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Evitar que una clasificación válida de servicio falle con HTTP 502 cuando el
proveedor omita el título o la descripción opcionales de la solicitud.

## Comportamiento requerido

1. Para una ruta `service`, el supervisor solicita un título breve y una
   descripción basada solo en el mensaje actual.
2. Si falta el título, se usa `Solicitud de atención`.
3. Si falta la descripción, se recupera el texto del último mensaje del cliente.
4. Si no hay descripción ni mensaje de cliente utilizable, se solicita una
   aclaración y no se crea el ticket.
5. La ruta de servicio continúa hacia el flujo técnico sin convertir esta salida
   incompleta del LLM en un error del patrón.
6. Los mensajes y sus contenidos no se agregan a las trazas de aplicación ni a
   los metadatos de LangSmith; las pruebas reales mantienen ocultos inputs y
   outputs.

## Criterios de aceptación

- Una respuesta `service` con `title` y `failure_description` ausentes crea el
  ticket usando el título genérico y el mensaje original como descripción.
- Sin mensaje de cliente utilizable, el supervisor responde con una aclaración
  y no persiste un ticket.
- El flujo jerárquico procesa el escenario de soporte sin terminar en `ValueError`.
