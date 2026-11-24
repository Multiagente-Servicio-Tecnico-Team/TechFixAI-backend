# 34. Evaluación piloto del RAG

## Ejecución desde la raíz

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_techfix --dry-run
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_techfix --limit 1
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_techfix
```

El primer comando solo recupera documentos locales. Los otros envían las preguntas, el contexto, las respuestas y las referencias de prueba a Groq. No ejecutar el ejemplo genérico `rag_eval/evals.py` ni instalar su pyproject para este piloto.

## Archivos

- `rag_eval/dataset_techfix.json`: siete casos, seis contestables y uno fuera del corpus; referencias basadas en el manual, pendientes de revisión humana.
- `rag_eval/evaluate_techfix.py`: evaluación secuencial con Faithfulness, ContextPrecision y ContextRecall. Guarda JSON y CSV después de cada caso en `.local/ragas/<fecha UTC>/`.
- `rag_eval/prueba_rag.py`: primera prueba individual, conservada.
- `rag_eval/requirements-lock.txt`: versiones del entorno de evaluación, independiente del backend.

## Validación local

Dry-run: boot_short 2 fragmentos; boot_natural 0; black_screen 1; disk_usage 2; cpu_usage 2; battery 3; out_of_scope 0. El caso natural original se conserva como fallo de recuperación. La ausencia de contexto del control se etiqueta como abstención esperada del recuperador; no demuestra una respuesta correcta del chat.

Una prueba individual previa de Faithfulness devolvió 0,60; no es el resultado del lote ni una cifra general del sistema. El juez usa max_tokens=8192 tras observar json_validate_failed con 1024.

## Interpretación y límites

Cada métrica tiene promedio y número de puntuaciones válidas. Los casos sin contexto y errores tienen null y quedan fuera del promedio: siempre informar también los estados y el total de casos. No comparar promedios sin sus denominadores.

El mismo modelo de Groq genera y juzga, lo que puede introducir sesgo. La evaluación usa recuperación real con un prompt específico de prueba, no el chat ni todos los patrones. Un piloto de siete preguntas no valida el corpus completo. Response Relevancy y su configuración de embeddings quedan pendientes.

El usuario autorizó explícitamente el envío de las referencias a Groq. La validación inicial de un caso terminó correctamente con Faithfulness 0,40, Context Precision aproximadamente 1,00 y Context Recall 1,00. La ejecución completa se registra por separado; estas cifras iniciales no son sus promedios.
## Texto base para el informe y capturas

### Preparación del entorno

Se preparó un entorno virtual independiente, denominado `.venv-ragas`, para ejecutar Ragas sin modificar las dependencias del backend de TechFixAI. Las versiones instaladas se registraron en `rag_eval/requirements-lock.txt`. Se verificó la consistencia de dependencias con `pip check` y la importación de Ragas. Para resolver incompatibilidades del entorno se utilizaron PyArrow 19.0.1, datasets 4.0.0 y langchain-community 0.3.31.

Captura sugerida: estructura de `rag_eval` y salida de `pip check`. Los archivos `rag.py` y `evals.py` son parte de la plantilla inicial; la evaluación de TechFixAI se ejecuta con `evaluate_techfix.py`.

### Preparación del conjunto de evaluación

Se elaboró un piloto de siete consultas sintéticas: seis relacionadas con casos técnicos del manual y una consulta fuera del dominio. Las respuestas de referencia se redactaron a partir de los casos 1, 2, 5, 6 y 9 de `manual_servicio.md`. Se incluyeron una consulta breve y una formulación natural extensa sobre el mismo error para observar la sensibilidad del recuperador a la redacción. Las referencias requieren revisión humana antes de utilizarse como benchmark definitivo.

Captura sugerida: `dataset_techfix.json`, mostrando `id`, `user_input`, `reference`, `source_case` y `answerable`.

### Integración con el recuperador y el evaluador

El script utiliza el recuperador compartido de TechFixAI, con un máximo de tres fragmentos por consulta y filtros para el área técnica y las fuentes clasificadas como guías verificadas. Los fragmentos se proporcionan a un prompt de prueba que solicita una respuesta en español basada únicamente en el contexto. La respuesta y el contexto se evalúan con Ragas 0.4.3 mediante el modelo `openai/gpt-oss-20b`, alojado en Groq. Las métricas de precisión y cobertura también reciben la respuesta de referencia. El modelo generador y el evaluador son el mismo, lo que constituye una limitación metodológica.

Captura sugerida: llamada a `retrieve_documents` y configuración de los tres scorers en `evaluate_techfix.py`. No mostrar el archivo `.env` ni claves.

### Métricas utilizadas

Faithfulness evalúa el respaldo de las afirmaciones de la respuesta en el contexto. Context Precision evalúa la utilidad y posición de los fragmentos recuperados respecto de la respuesta de referencia. Context Recall evalúa cuánto de la respuesta de referencia está respaldado por el contexto recuperado. Las puntuaciones válidas se expresan en una escala de cero a uno; los errores y casos sin contexto se registran con valores nulos y se presentan por separado.

Captura sugerida: terminal de la ejecución y tabla de `results.csv`. Informar el número de casos evaluados por cada métrica junto con sus promedios.

### Alcance

Esta prueba evalúa el recuperador real y una generación controlada mediante un prompt de prueba. No evalúa el flujo completo del chat autenticado, la persistencia de tickets ni las diferencias entre los tres patrones multiagente. Los archivos JSON contienen los contextos y respuestas sintéticos necesarios para revisar los resultados; se almacenan como evidencia local, separados de las trazas operativas.


Observación del lote: el caso disk_usage registró APIStatusError HTTP 413 en Faithfulness; sus otras métricas se conservaron. Este estado se informa por separado, sin inventar una puntuación ni borrar el caso. El 413 indica rechazo por tamaño; no confirma agotamiento de saldo.

## Resultados verificados del piloto completo (2026-11-11)

Evidencia: `.local/ragas/20261111T060317567694Z/results.json` y `results.csv`. Esta corrida es distinta de la prueba individual inicial. Se procesaron los siete casos; no se modificaron sus preguntas para mejorar las puntuaciones.

| Caso | Contextos | Faithfulness | Context Precision | Context Recall | Observación |
| --- | ---: | ---: | ---: | ---: | --- |
| boot_short | 2 | 0,455 | 1,000 | 1,000 | Tres puntuaciones válidas |
| boot_natural | 0 | — | — | — | Pregunta contestable sin contexto recuperado |
| black_screen | 1 | 0,429 | 1,000 | 1,000 | Tres puntuaciones válidas |
| disk_usage | 2 | — | 1,000 | 1,000 | Faithfulness falló: HTTP 413 |
| cpu_usage | 2 | — | 1,000 | 1,000 | Faithfulness falló: HTTP 400 |
| battery | 3 | — | 1,000 | 1,000 | Faithfulness falló: HTTP 400 |
| out_of_scope | 0 | — | — | — | Ausencia de recuperación esperada en el control |

Los valores de Context Precision cercanos a uno se redondean a tres decimales; los originales se conservan en JSON.

| Métrica | Promedio válido | Casos puntuados |
| --- | ---: | ---: |
| Faithfulness | 0,442 | 2 |
| Context Precision | 1,000 | 5 |
| Context Recall | 1,000 | 5 |

De seis preguntas técnicas contestables, cinco recuperaron contexto y una no. La pregunta de control fuera del corpus no recuperó fragmentos, pero eso no evalúa la respuesta del chat porque el script no genera una respuesta en ausencia de contexto. Tres casos tuvieron evaluaciones de fidelidad fallidas y sus puntuaciones se dejaron nulas. Los valores faltantes no se reemplazaron por cero ni por uno.

### Párrafo de resultados listo para adaptar al informe

Se ejecutó una evaluación piloto con siete consultas sintéticas mediante Ragas. Cinco de las seis consultas técnicas recuperaron contexto; la formulación natural extensa del error de arranque no recuperó fragmentos. La consulta de control, ajena al corpus técnico, tampoco recuperó información. En los cinco casos puntuables para recuperación, Context Precision y Context Recall alcanzaron valores medios redondeados de 1,000. Faithfulness obtuvo un promedio de 0,442 sobre dos casos válidos; las otras tres evaluaciones de fidelidad fallaron con respuestas HTTP 413 o 400 del proveedor y se registraron sin puntuación. Por ello, los promedios se presentan con su cantidad de observaciones válidas y no se interpretan como una medida global de calidad del sistema.

La revisión de una respuesta de pantalla negra mostró que el prompt de prueba generó instrucciones detalladas de manipulación de memoria y BIOS que no estaban explicitadas en el fragmento recuperado. Esto ilustra la necesidad de evaluar por separado la recuperación y el respaldo de las afirmaciones generadas. La prueba utiliza un prompt específico y no permite atribuir directamente ese comportamiento al chat completo. El uso del mismo modelo para generar y evaluar, el tamaño reducido del dataset y las referencias pendientes de revisión humana limitan las conclusiones.

### Capturas para el informe

1. Preparación: carpeta `rag_eval` y `requirements-lock.txt`.
2. Dataset: abrir `rag_eval/dataset_techfix.json` y mostrar pregunta, referencia y caso de origen.
3. Integración: mostrar los filtros de `retrieve_documents` y las tres métricas en `rag_eval/evaluate_techfix.py`.
4. Evidencia: abrir el `results.csv` de esta corrida; la columna `status` debe permanecer visible junto a las puntuaciones.
5. Análisis: mostrar esta tabla de resultados y los denominadores. No presentar valores nulos como pruebas aprobadas.
