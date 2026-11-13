# 37. Evaluación automática del RAG: Ragas, BLEU y ROUGE

## Rama y alcance confirmado

Implementación en la rama local `eval/rag-baseline`, desde `f274d2b0328e6780cada2804514a3470c96e9614` (`test: incorporar evaluacion del RAG`). El evaluador ya estaba versionado en ese commit. Se conservaron `rag_eval/evals.py` y `rag_eval/rag.py`, ejemplos locales sin seguimiento; no se incorporaron al flujo. Se revisaron ramas remotas y el PR abierto #42 de domain-guard; no se fusionó ni publicó nada.

No se modificó `app/`, corpus, ranking, prompts, requisitos raíz ni arranque. La implementación está en `rag_eval/baseline.py`, `baseline_state.py`, `baseline_report.py`, `text_metrics.py` y `extended_metrics.py`. Los módulos anteriores y sus corridas permanecen conservados. Las pruebas nuevas están en `tests/unit/rag/test_rag_baseline.py`.

El recorrido técnico real es `runtime.prepare_case` → `make_knowledge_retrieval_agent(MarkdownKnowledgeRetriever())` → `make_technical_support_agent` → `create_model`/ChatGroq mediante el adaptador nativo con caché. Se ejecutan el prompt y JSON mode originales; se puntúa `provisional_diagnosis`. El estado inicial tiene una pregunta sintética y no reproduce una conversación previa. Para FAQ se ejecuta `MarkdownFaqRetriever.retrieve` → `answer_faq` con su prompt y truncado originales. No se ejecutan API HTTP, autenticación, supervisores, herramientas comerciales ni PostgreSQL; no es validación integral de los tres grafos.

`ContextRecordingModel` comprueba el mensaje de sistema que realmente recibe el adaptador del generador. Guarda el contexto exacto, sus fragmentos ordenados y el hash de los mensajes; no modifica mensajes ni método de salida. Las respuestas de caché se identifican como reutilizadas. Para las históricas se comprueban las fuentes y la implementación nativa original, además de preguntas y contextos exactos. El generador es `openai/gpt-oss-20b` con parámetros del backend; el juez es `openai/gpt-oss-120b`.

## Dataset y auditoría histórica

Dataset conservado: `rag_eval/dataset_project.json`, esquema v2, 30 preguntas: 20 técnicas, 8 FAQ y 2 fuera del corpus. Las referencias son extractos verificados contra los archivos Markdown, no respuestas revisadas independientemente por humanos. Se conservaron sin redactarlas en función de las respuestas obtenidas.

Inventario por ID y hashes: `.local/ragas/baseline-audit/historical_inventory.json`.

La corrida principal `project-20261111T081747383016Z` contiene exactamente nueve respuestas puntuadas, tres consultas técnicas sin contexto y un caso detenido por cuota; faltaban 16 respuestas entre los 25 casos con contexto. Otras 17 preguntas no habían sido procesadas por ese script. Su resumen `answerable=13` describe solo las filas guardadas, no los 28 casos contestables del dataset.

La prueba nativa `project-20261111T081539787992Z` conserva una respuesta técnica ya presente y `faq_payments`; al importar ambas corridas se añaden diez respuestas únicas compatibles, no once. Por eso quedan **15 respuestas con contexto pendientes**. Una de ellas conserva el bloqueo histórico por cuota de 20B; en esta entrega no se volvió a intentar esa generación y no se afirma que la cuota actual siga agotada.

La corrida `project-20261111T065531240946Z`, con generador y juez 120B, sigue independiente e intacta. No se importaron sus respuestas a la línea base 20B. Sus juicios de recuperación se pueden reutilizar únicamente como aciertos exactos de la caché del mismo juez y prompt, con pregunta, referencia y fragmentos idénticos; no dependen de la respuesta generada.

## Métricas y reproducibilidad

Ragas instalado: 0.4.3. Se verificó por introspección que `ContextPrecision` hereda de `ContextPrecisionWithReference`. Se conservan Context Recall y Faithfulness, y se incorporan `AnswerRelevancy` (columna `response_relevancy`, strictness=3) y `FactualCorrectness` en modo F1 (beta=1, atomicity=low, coverage=low). Se conservan instrucciones originales, sin ejemplos few-shot; el juez usa JSON Schema estricto, temperature=0, reasoning_effort=low y máximo 4096 tokens. La caché de las tres inferencias de relevancia usa slots separados: no reutiliza una sola inferencia como si fueran tres distintas.

Embeddings del evaluador: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, repositorio ONNX `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`, revisión `faf4aa4225822f3bc6376869cb1164e8e3feedd0`. FastEmbed 0.7.4, CPU, 384 dimensiones, mean pooling, sin prefijos. Los archivos de pesos/tokenizador y sus hashes se guardan en `.local/ragas/embeddings/multilingual-minilm/embedding_manifest.json`; la puntuación requiere ese snapshot local y comprueba hashes y versiones. Preparar embeddings descarga pesos públicos; no envía preguntas a un servicio de embeddings.

SacreBLEU 2.5.1: BLEU-4 de corpus principal, BLEU-1/2/3 como detalle, tokenización 13a, minúsculas, suavizado exponencial, effective_order=False. Se registran orden máximo, firma, longitudes y penalización de brevedad. Escala 0–100. Los filtros de texto determinan qué preguntas tienen ROUGE calculado y entran en BLEU de corpus; el reporte acumula resultados guardados de los IDs ya puntuados.

ROUGE Score 0.1.2: ROUGE-1/2/L, precisión/recall/F1 por caso y macro media de F1. Tokenizador propio Unicode NFC/casefold, sin stemmer. Ejemplo verificado: `Diagnóstico: daño, conexión 0x0000007B SSD_1TB` produce `diagnóstico`, `daño`, `conexión`, `0x0000007b`, `ssd_1tb`. No se eliminan tildes ni se fragmenta el código hexadecimal.

Los resultados guardan commit, rama, hashes del dataset y fuentes, versión del dataset, perfil del generador, versiones instaladas, Python/plataforma, hash del lock y perfiles de puntuación/embeddings. La reanudación rechaza cambios de configuración/fuentes/dependencias relevantes. El código de generación también está identificado por hash: si cambia después de producir evidencia, crear otra corrida conservando la anterior.

La reproducción con entradas y juicios guardados evita nuevas variaciones del proveedor. Una corrida fresca del LLM puede variar incluso con temperatura cero; los IDs de modelo no garantizan inmutabilidad del servicio remoto.

Se corrigió el requisito declarado `openai>=2` a `openai==1.109.1`, que es la versión realmente utilizada y registrada en la evidencia histórica y el lock. Nuevas dependencias únicamente en `.venv-ragas` y `rag_eval/`; FastEmbed es extra opcional. No se actualizó la dependencia del backend.

## Comandos PowerShell

Ejecutar desde la raíz del repositorio; no hace falta cambiar el entorno activo si se usa la ruta explícita del Python.

Instalación reproducible en un entorno nuevo de evaluación:

```powershell
py -3.13 -m venv .venv-ragas
.\.venv-ragas\Scripts\python.exe -m pip install -r .\rag_eval\requirements-lock.txt
```

Auditar evidencia y preparar explícitamente los embeddings (solo hace falta descargarlos una vez):

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline audit
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline prepare-embeddings
```

Crear una corrida aprovechando las respuestas nativas históricas verificadas, sin nuevas generaciones:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline generate --run .local/ragas/baseline-v1-final --prepare-only --reuse-run .local/ragas/project-20261111T081747383016Z --reuse-run .local/ragas/project-20261111T081539787992Z
```

Generar un siguiente caso para controlar consumo:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline generate --run .local/ragas/baseline-v1-final --only technical_07_short
```

Continuar los restantes o reanudar después de un error/cuota (el mismo comando conserva todos los casos terminados):

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline generate --run .local/ragas/baseline-v1-final
```

Puntuar solo BLEU/ROUGE, sin Groq ni cargar embeddings:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline score --run .local/ragas/baseline-v1-final --group text
```

Puntuar Ragas o todas las métricas sobre las mismas respuestas guardadas:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline score --run .local/ragas/baseline-v1-final --group ragas
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline score --run .local/ragas/baseline-v1-final --group all
```

Recalcular únicamente con juicios existentes, prohibiendo llamadas al juez:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline score --run .local/ragas/baseline-v1-final --group all --cache-only
```

Si no existe un juicio, queda `cache_miss`; no se interpreta como cero ni como cuota. Para terminar esos juicios, repetir sin `--cache-only`. Código de salida Python: 0 para selección completada, 2 para pendientes/cuota y 1 para error; algunos wrappers PowerShell pueden presentar un código de proceso genérico.

Reproducir la prueba pequeña (el directorio nuevo contiene los 30 casos preparados, pero solo ejecuta los tres IDs seleccionados):

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline generate --run .local/ragas/baseline-smoke-v1-final --only technical_01_short faq_payments control_sports
.\.venv-ragas\Scripts\python.exe -m rag_eval.baseline score --run .local/ragas/baseline-smoke-v1-final --group all --only technical_01_short faq_payments control_sports
```

Se puede añadir `--limit 3` en generación o puntuación. El límite selecciona los primeros IDs del dataset, incluidos los ya completados; para avanzar a otros casos usar `--only` o quitar el límite. Para empezar desde cero usar otro directorio `--run`. Las claves se leen mediante la configuración local del proyecto; no se escriben en evidencias ni comandos.

## Evidencia y resultados

Lote consolidado: `.local/ragas/baseline-v1-final/`. Prueba pequeña: `.local/ragas/baseline-smoke-v1-final/`. Cada directorio contiene:

- `results.json`: preguntas, referencias, fuentes, respuestas, contextos recuperados y realmente entregados, orden, estados, errores seguros y procedencia.
- `results.csv`: una fila por ID, métricas de respuesta/recuperación, ROUGE precisión/recall/F1 y estados.
- `summary.json`: cobertura, medias, desviación poblacional, errores y BLEU de corpus; grupos all, technical, faq y out_of_corpus.
- `report.md`: resumen legible, denominadores y estado por ID.

Los archivos detallados y los pesos permanecen en `.local`, excluido de Git. Las métricas no aplicables no reciben ceros. La recuperación se puntúa aunque falte respuesta. Una respuesta válida sin contexto puede recibir relevancia, Factual Correctness y texto si tiene las entradas necesarias. Cuando el componente no produce ninguna respuesta por falta de contexto, esas métricas quedan no aplicables y el fallo de recuperación sigue visible.

### Prueba pequeña

Los tres IDs terminaron correctamente. Las dos respuestas contestables se obtuvieron ejecutando los componentes reales y reutilizando dos aciertos de caché nativa verificados (cero llamadas nuevas al generador). El control FAQ devolvió su abstención determinista. Repetir generación conservó las respuestas, con cero llamadas y cero filas duplicadas.

La primera puntuación de las métricas nuevas utilizó Groq 120B (20 llamadas de juez en el piloto, sin errores). La evidencia final reproduce esos juicios desde caché y los embeddings locales. No se consumió generación 20B nueva ni se comprobó su cuota actual.

| Métrica | Resultado | Casos válidos |
| --- | ---: | ---: |
| Context Precision | 1.0000 | 2 |
| Context Recall | 1.0000 | 2 |
| Faithfulness | 1.0000 | 2 |
| Response Relevancy | 0.4355 | 3 |
| Factual Correctness F1 | 0.6350 | 2 |
| ROUGE-1 F1 | 0.4953 | 2 |
| ROUGE-2 F1 | 0.3769 | 2 |
| ROUGE-L F1 | 0.4342 | 2 |
| BLEU1 corpus (0–100) | 30.8730 | 2 |
| BLEU2 corpus (0–100) | 26.7986 | 2 |
| BLEU3 corpus (0–100) | 24.5593 | 2 |
| BLEU4 corpus (0–100) | 22.6612 | 2 |

Relevancia incluye el control (cero por abstención); su media solo entre los dos contestables es 0,6532. Para el control no aplican BLEU/ROUGE ni las métricas con referencia; Faithfulness tampoco aplica sin contexto. No interpretar esta prueba de tres IDs como calidad global del RAG.

Validación de reanudación y aislamiento: `.local/ragas/baseline-smoke-v1-final/validation.json`. Prueba de texto con red/imports de proveedores bloqueados: `.local/check_text_offline.py` y `.local/offline-text-validation.log`.

### Lote consolidado parcial

Recuperación con contexto: 25/28 contestables. Respuestas: diez contestables y una abstención del control FAQ. Quedan quince generaciones contestables con contexto pendientes; tres consultas no recuperaron contexto. El control técnico no produjo respuesta en este recorrido aislado.

| Métrica | Resultado | Casos válidos |
| --- | ---: | ---: |
| Context Precision | 0.9600 | 25 |
| Context Recall | 0.9520 | 25 |
| Faithfulness | 0.9909 | 10 |
| Response Relevancy | 0.4355 | 3 |
| Factual Correctness F1 | 0.6350 | 2 |
| ROUGE-1 F1 | 0.5208 | 10 |
| ROUGE-2 F1 | 0.3701 | 10 |
| ROUGE-L F1 | 0.4434 | 10 |
| BLEU1 corpus (0–100) | 50.8452 | 10 |
| BLEU2 corpus (0–100) | 41.1020 | 10 |
| BLEU3 corpus (0–100) | 35.7101 | 10 |
| BLEU4 corpus (0–100) | 31.7947 | 10 |

Esta consolidación reutiliza solo respuestas 20B compatibles, sus métricas históricas verificadas y juicios idénticos en caché. Cero llamadas nuevas a proveedores al consolidar. Las ocho respuestas sin juicios nuevos se distinguen como `cache_miss`, no como fallos de API ni ceros.

### Estado verificado de los 30 IDs

| ID | Estado en corrida principal histórica | Contextos actuales | Estado consolidado |
| --- | --- | ---: | --- |
| technical_01_short | ok | 1 | ok |
| technical_01_natural | ok | 1 | ok |
| technical_02_short | ok | 1 | ok |
| technical_02_natural | no_context | 0 | no_context |
| technical_03_short | ok | 1 | ok |
| technical_03_natural | no_context | 0 | no_context |
| technical_04_short | ok | 1 | ok |
| technical_04_natural | no_context | 0 | no_context |
| technical_05_short | ok | 2 | ok |
| technical_05_natural | ok | 2 | ok |
| technical_06_short | ok | 1 | ok |
| technical_06_natural | ok | 1 | ok |
| technical_07_short | quota_exhausted | 1 | quota_pending |
| technical_07_natural | not_processed | 1 | pending |
| technical_08_short | not_processed | 2 | pending |
| technical_08_natural | not_processed | 1 | pending |
| technical_09_short | not_processed | 1 | pending |
| technical_09_natural | not_processed | 1 | pending |
| technical_10_short | not_processed | 1 | pending |
| technical_10_natural | not_processed | 2 | pending |
| faq_services | not_processed | 2 | pending |
| faq_location | not_processed | 1 | pending |
| faq_hours | not_processed | 1 | pending |
| faq_quotes | not_processed | 2 | pending |
| faq_payments | not_processed | 1 | ok |
| faq_warranty | not_processed | 2 | pending |
| faq_delivery | not_processed | 1 | pending |
| faq_inventory | not_processed | 1 | pending |
| control_recipe | not_processed | 0 | not_applicable |
| control_sports | not_processed | 0 | ok |

## Interpretación y pendientes

Se mantienen separados recuperación, respuesta y coincidencia textual. La media de relevancia de controles no mide calidad de abstención: una abstención correcta puede obtener cero al no responder una pregunta ajena al dominio. Consultar también el desglose técnico/FAQ y el registro explícito de abstención.

Las referencias conservan extractos amplios del manual y de FAQ, mientras el prompt técnico exige diagnóstico breve/provisional y precauciones. Esa diferencia de extensión/contenido influye en BLEU, ROUGE y Factual Correctness. Los valores no equivalen a exactitud clínica/técnica ni a validación comercial; referencias, datos de FAQ y criterio de respuesta necesitan revisión independiente antes de conclusiones más amplias.

Pendiente para completar el lote actual: generar los 15 casos contestables con contexto restantes y ejecutar las métricas de respuesta faltantes. Ocho respuestas ya disponibles todavía requieren nuevos juicios de relevancia y Factual Correctness, no presentes en caché. Las tres consultas sin contexto se registran como fallos de recuperación; su solución pertenece a una comparación posterior, sin alterar esta línea base. El control técnico sin respuesta no permite afirmar que el chat completo se abstuvo.

## Validación local

Suite aislada de RAG: **47 aprobadas**, incluidas 15 nuevas del evaluador. `pip check`, `compileall` y `git diff --check` correctos. Se verifican reanudación, referencias incompatibles, API de métricas, no confundir ausentes con ceros, orden real del contexto y tres posiciones independientes de caché para relevancia. La prueba BLEU/ROUGE funcionó con red y módulos de backend/proveedores bloqueados. Se verificaron por hash las corridas históricas, incluida 120B, sin alteraciones. No se repite la suite general del backend porque no cambió `app/`; conserva los cinco errores de fixture ya documentados en la tarea 36.

Fuentes: [Ragas: métricas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/), [SacreBLEU](https://github.com/mjpost/sacrebleu), [ROUGE](https://github.com/google-research/google-research/tree/master/rouge), [FastEmbed: modelos](https://qdrant.github.io/fastembed/examples/Supported_Models/).
