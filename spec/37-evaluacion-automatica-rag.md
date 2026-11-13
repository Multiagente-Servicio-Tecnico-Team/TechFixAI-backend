# 37. Evaluación automática reproducible del RAG existente

## Alcance

Ampliar el evaluador existente con generación/puntuación separadas, recuperación reanudable y métricas Ragas, BLEU y ROUGE. Conservar dataset v2 (30 IDs: 20 técnicos, 8 FAQ, 2 controles), corpus, recuperador, prompts, configuración del backend y evidencia histórica.

Evaluar diagnóstico técnico jerárquico (`prepare_case` → agente real de recuperación → agente real de soporte) y FAQ compartida (`MarkdownFaqRetriever` → `answer_faq`). Usar `create_model` y sus parámetros originales mediante `NativeProjectModel`; verificar que el mensaje de sistema incluya exactamente los fragmentos guardados, en su orden. Medir el campo `provisional_diagnosis` y la respuesta FAQ, no la conversación HTTP completa, sesión, supervisores ni persistencia.

## Requisitos

1. Rama local `eval/rag-baseline` desde `f274d2b0328e6780cada2804514a3470c96e9614`; conservar archivos locales, sin commit/push/deploy.
2. Inventariar evidencia histórica por ID; importar respuestas solo con dataset, fuentes, modelo, transporte, perfil, dependencias de generación y contextos compatibles. No importar respuestas del generador 120B a la línea base 20B.
3. Persistir cada caso y reanudar sin regenerar terminados; filtrar por IDs o límite. Detectar cambios de configuración y rechazar reanudaciones incompatibles.
4. Puntuar entradas guardadas independientemente de generación: recuperación aunque falle la respuesta; Factual Correctness, relevancia y texto con respuesta válida aunque falte contexto.
5. Ragas 0.4.3: ContextPrecision (subclase de ContextPrecisionWithReference), ContextRecall, Faithfulness, AnswerRelevancy (expuesta como response_relevancy), FactualCorrectness(mode=f1). Reutilizar juez estricto y caché; conservar instrucciones originales sin ejemplos. Registrar perfil exacto.
6. Relevancia: embeddings locales multilingües, snapshot y hashes verificados, CPU, sin descargas implícitas al puntuar. Tres inferencias del juez conservan posiciones de caché distintas, sin cambiar su prompt ni la fórmula Ragas.
7. BLEU de corpus SacreBLEU: órdenes máximos 1, 2, 3, 4; principal BLEU-4; tokenización 13a, lowercase, suavizado exp, effective_order=False, escala 0–100, firmas y penalización de brevedad. Nunca promediar BLEU por pregunta para obtener el global.
8. ROUGE-1/2/L: precisión, recall y F1 por pregunta; macro media F1; tokenización Unicode NFC/casefold que conserve tildes, ñ, hexadecimales y códigos con guion bajo. Sin stemming.
9. Separar estado de recuperación, generación y de cada métrica. Distinguir pendiente, cuota, error API, sin contexto, no aplicable, dependencia pendiente y falta de caché; no inventar ceros. No confundir falta de contexto con abstención emitida.
10. Informes JSON con respuestas/contextos, CSV por pregunta, JSON de resumen y Markdown, con cobertura por métrica y desglose técnico/FAQ/controles.

## Validación

Prueba pequeña: `technical_01_short`, `faq_payments`, `control_sports`; comprobar puntuaciones, abstención FAQ, no aplicabilidad de métricas con referencia para controles y reanudación sin llamadas ni duplicados. Pruebas aisladas para procedencia, contexto real, variantes de métricas, estados, Unicode, BLEU de corpus y caché independiente. Confirmar `app/` y requisitos principales sin cambios. Evidencia y comandos en `docs/37-evaluacion-automatica-rag.md`.
