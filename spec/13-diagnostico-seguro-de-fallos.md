# Spec 13 — Diagnóstico seguro de fallos del grafo

**Estado retrospectivo: Implementada según evidencia histórica; no se reejecutaron pruebas en esta revisión.**
**Evidencia revisada:** docs/16-diagnostico-seguro-de-fallos.md; app/agents/jerarquico/trace.py
**Alcance de esta revisión:** inspección estática; no se ejecutaron pruebas ni servicios. Ver [README.md](README.md) para el criterio y el flujo Spec Kit.


## Objetivo

Permitir ubicar con mayor precisión errores de nodos y herramientas sin registrar
mensajes del cliente, parámetros/resultados, texto SQL, credenciales ni textos de
excepciones.

## Requisitos

- Mantener los eventos JSONL con timestamp, execution ID, nombre permitido,
  componente y evento.
- En eventos `error`, agregar solo el nombre de la clase de excepción y, si
  PostgreSQL lo entrega, un SQLSTATE de cinco caracteres alfanuméricos.
- Mostrar tipo de excepción y SQLSTATE seguro en el log del backend.
- Mantener el texto de excepción redactado en LangSmith y en la respuesta HTTP.
- No exponer el mensaje de excepción, SQL, parámetros ni resultados en trazas.

## Criterios de aceptación

- Un error PostgreSQL puede correlacionarse con nodo/herramienta y SQLSTATE.
- Errores sin código incluyen solo su tipo.
- Las pruebas comprueban que un mensaje privado de excepción no aparece en el
  JSONL y que un SQLSTATE válido sí se conserva.
