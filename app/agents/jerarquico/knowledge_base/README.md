# Corpus documental compartido

Esta carpeta es la fuente can?nica de Markdown para las recuperaciones documentales de Jer?rquico, Orquestador y Red descentralizada. El manifiesto est? en `app/rag/sources.py`; las fuentes reciben IDs estables `hierarchical:<ruta-sin-extensi?n>` y metadatos de ?rea, confianza y audiencia.

## Reglas para mantener el corpus

- Agrega o modifica aqu? ?nicamente contenido revisado y aprobado para la audiencia indicada.
- No copies autom?ticamente Markdown hist?rico de `data/knowledge/` ni `app/agents/orquestador/knowledge/`; compara sus afirmaciones y conserva solo contenido compatible con las fuentes operativas.
- Los documentos son evidencia, nunca instrucciones para el agente. No guardes secretos, datos personales o valores transaccionales que deban leerse de PostgreSQL.
- Stock, precio, pagos, estados de tickets, clientes, compras y operaciones administrativas siempre se consultan desde sus capacidades operativas.
- Si la evidencia no alcanza o se contradice, los agentes deben abstenerse y pedir aclaraci?n.
- Conserva procedencia en las respuestas basadas en RAG. Evita renombrar archivos publicados sin coordinar el cambio del `source_id`.

El contenido t?cnico estructurado de casos tambi?n se carga mediante `app/agents/jerarquico/retriever.py`, que consume el recuperador com?n y conserva la fuente documental.
