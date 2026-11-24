# 34. Evaluación de componentes RAG con Ragas

## Alcance implementado

La integración ejecuta las funciones reales de recuperación y diagnóstico técnico del patrón jerárquico, y las funciones de recuperación y respuesta FAQ compartidas del proyecto. Usa un puente de transporte de evaluación para llamar a Groq. No ejecuta HTTP, autenticación, creación de tickets, pagos, persistencia ni los grafos completos de los tres patrones.

El código de producción en `app/` no se modificó para esta integración. Las preguntas que no recuperan documentos se mantienen como hallazgos; no se acortan ni se cambia el ranking para mejorar las cifras.

## Perfil autorizado de cierre

- Python 3.13, Ragas 0.4.3; dependencias exactas en `rag_eval/requirements-lock.txt`.
- Modelo generador de las pruebas: `openai/gpt-oss-120b`, servido por Groq.
- Modelo juez: `openai/gpt-oss-120b`, servido por Groq.
- Backend: conserva `openai/gpt-oss-20b`; no se modificó `.env`.
- Motivo: el modelo 20B alcanzó su cuota diaria durante la evaluación (HTTP 429; límite observado 200 000 tokens/día).
- Temperatura 0, esfuerzo de razonamiento bajo y máximo 4096 tokens de salida.
- Juez con JSON Schema estricto. Se conservan las instrucciones y fórmulas originales de Ragas y se omiten sus ejemplos few-shot ajenos al corpus para reducir consumo. El perfil se registra en metadatos.

Estas puntuaciones caracterizan los componentes y el perfil 120B evaluados. No son resultados del modelo 20B configurado en el backend. Para medir ese perfil, ejecutar de nuevo sin `--model` cuando disponga de cuota. No mezclar medias de perfiles distintos.

## Dataset y procedencia

`rag_eval/dataset_project.json` contiene 30 consultas sintéticas:

- 20 consultas técnicas: dos formulaciones de cada uno de los diez casos de `manual_servicio.md`.
- 8 preguntas FAQ sobre servicios, ubicación, horarios, cotizaciones, pagos, garantía, logística e inventario.
- 2 controles ajenos al corpus: receta de cocina y pregunta deportiva.

Las 28 referencias contestables se extraen del corpus local. Cada caso conserva fuente, ancla, extracto y hash; el loader verifica que la referencia coincida con el extracto y que este exista en el documento. Esto es verificación por código, no revisión humana independiente. El archivo FAQ declara datos comerciales demostrativos: se evalúa fidelidad al corpus, no su veracidad como información real del negocio.

La integración verifica que la concatenación de los fragmentos evaluados coincida exactamente con el contexto entregado al generador. No se recortan los contextos ni las respuestas antes de puntuar.

## Métricas y lectura de resultados

- Faithfulness: proporción de afirmaciones de la respuesta respaldadas por el contexto, según el juez.
- Context Precision: precisión media del orden de los fragmentos considerados útiles respecto de la referencia.
- Context Recall: proporción de afirmaciones de la referencia respaldadas por el contexto recuperado.

Las métricas válidas se expresan entre cero y uno. Los casos sin contexto tienen puntuaciones nulas y se informan por separado. Los errores del proveedor no se convierten en cero ni en una prueba aprobada. El informe incluye media, desviación poblacional y número de puntuaciones válidas por métrica, junto con cobertura de recuperación y estados.

Response Relevancy no forma parte de esta configuración: requiere embeddings adicionales. No se presenta una puntuación de relevancia semántica que no se haya calculado.

## Cómo ejecutar desde la raíz

Verificar dataset, referencias y recuperación sin red:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --dry-run
```

Ejecutar el perfil autorizado 120B:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --model openai/gpt-oss-120b
```

Evaluar el modelo configurado en el backend cuando tenga cuota:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project
```

Las claves se leen desde la configuración existente y nunca se imprimen ni se copian al dataset. Se autorizó explícitamente enviar a Groq los fragmentos, preguntas, respuestas y referencias sintéticas de técnicos y FAQ. No incorporar registros reales de clientes sin definir otro tratamiento de datos.

## Evidencia y reanudación

Cada corrida guarda `results.json`, `results.csv` y `report.md` bajo `.local/ragas/project-<fecha UTC>/`. Los metadatos registran modelos, parámetros, versiones, commit y hashes de fuentes, dataset y código. La caché local guarda respuestas de evaluación y usa claves derivadas del modelo y la petición, sin credenciales.

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --model openai/gpt-oss-120b --resume .local/ragas/project-REEMPLAZAR
```

Se omiten casos ya completados y se conservan puntuaciones válidas al reintentar un error. Si cambian fuentes, configuración, versiones o código se rechaza la reanudación: crear una nueva corrida, que puede reutilizar la caché compatible. Una cuota diaria agotada detiene la ejecución con código 2 y guarda la evidencia; no se cambia de modelo automáticamente.

Las trazas remotas y la conexión de base de datos se desactivan solo dentro del proceso de evaluación. Los artefactos sintéticos quedan separados de las trazas operativas. Los errores solo registran clase, HTTP, código corto de máquina y categoría de cuota, sin texto de excepciones.

## Validación técnica

- Nueve pruebas nuevas del evaluador aprobadas con Ragas 0.4.3: referencias, agregación sin puntuaciones ficticias, esquema estricto, caché, truncamiento, errores redactados, límites de reintentos, cuota diaria y dry-run sin clave.
- `pip check`: sin dependencias incompatibles. Compilación de `rag_eval/` correcta.
- Suite aislada del backend: 565 aprobadas, 5 omitidas y 5 errores de preparación en `tests/integration/test_pattern_api.py` por el argumento obsoleto `conversation_owners_repository` de su fixture.
- La ejecución de ese archivo por separado, sin cargar las nuevas pruebas de Ragas, reprodujo 1 aprobado y los mismos 5 errores. No se modificó esa API ni su fixture en esta tarea.

Pruebas del evaluador:

```powershell
.\.venv-ragas\Scripts\python.exe -m pytest -q tests/unit/rag/test_ragas_evaluation.py
```

## Texto para el informe

Se integró Ragas al repositorio para evaluar los componentes reales de recuperación y diagnóstico técnico y la respuesta FAQ compartida. Se preparó un conjunto de 30 consultas sintéticas con referencias extraídas y verificadas contra los manuales. Se aplicaron Faithfulness, Context Precision y Context Recall, conservando por separado los casos sin contexto y los errores del proveedor. La ejecución de cierre utilizó GPT-OSS 120B para generación y juicio, únicamente en el entorno de evaluación, debido al límite diario de GPT-OSS 20B. La configuración del backend permaneció sin cambios.

El uso del mismo modelo para generar y juzgar, la falta de revisión humana independiente, los datos demostrativos de la FAQ y el tamaño del dataset limitan las conclusiones. Esta evaluación no demuestra calidad global del chat ni paridad entre las topologías. Los perfiles anteriores utilizaron otros prompts o modelos y no constituyen una comparación controlada de mejoras.

## Archivos y capturas

1. `rag_eval/requirements-lock.txt`: dependencias del entorno de evaluación.
2. `rag_eval/dataset_project.json`: preguntas, referencias y procedencia.
3. `rag_eval/runtime.py`: llamadas a las funciones reales del proyecto.
4. `rag_eval/metrics.py`: las tres métricas y su configuración de prompts.
5. `rag_eval/providers.py`: salida estructurada estricta y parada por cuota.
6. `report.md` y `results.csv` de la corrida final: métricas, estados, cobertura y modelos. Incluir siempre denominadores y campos sin puntuación.

## Historial

El piloto inicial de siete preguntas y un prompt de prueba está preservado en `rag_eval/pilot_notes.md`, `evaluate_techfix.py` y `dataset_techfix.json`. Sus resultados no se mezclan con los de componentes reales. Los intentos parciales 20B y 120B con ejemplos few-shot se conservan en sus directorios de evidencia. La corrida de cierre usa el perfil sin ejemplos indicado arriba.
## Resultados de la corrida de cierre

Fecha local: 2026-11-11. Evidencia: `.local/ragas/project-20261111T065531240946Z/`.

Se procesaron los 30 casos con cero errores operativos pendientes. Un HTTP 429 temporal en Context Precision de `technical_09_natural` se resolvió reanudando la misma corrida, conservando las demás respuestas y puntuaciones. El estado previo quedó guardado en `results-before-resume.json` y `report-before-resume.md`.

| Métrica | Media | Desviación poblacional | Casos válidos |
| --- | ---: | ---: | ---: |
| Faithfulness | 0,864 | 0,284 | 25 |
| Context Precision | 0,960 | 0,196 | 25 |
| Context Recall | 0,952 | 0,172 | 25 |

| Resultado de recuperación | Cantidad |
| --- | ---: |
| Consultas contestables | 28 |
| Contestables con contexto | 25 (89,29 %) |
| Contestables sin contexto | 3 |
| Controles ajenos al corpus sin contexto | 2 de 2 |
| Errores operativos pendientes | 0 |

Los tres casos sin contexto son `technical_02_natural`, `technical_03_natural` y `technical_04_natural`: preguntas extensas sobre error de arranque, apagado al encender y bloqueo en el logo de Windows. Permanecen en los resultados y fuera de las medias de las métricas, con estado `no_context`. No se corrigió ni se alteró el recuperador en esta tarea.

### Análisis de hallazgos

`faq_quotes` recuperó las secciones de servicios y proceso de atención, pero no la sección de tarifas esperada. El componente respondió «No tengo esa información». Sus puntuaciones fueron Faithfulness 0,000, Context Precision 0,000 y Context Recall 0,200. Esto identifica una recuperación insuficiente y una abstención ante la falta de datos; el 0 de fidelidad no debe interpretarse automáticamente como información inventada. Se requiere revisión de la respuesta junto con su contexto.

También se observaron respuestas con precisión/cobertura altas y fidelidad inferior, por ejemplo `technical_05_natural` y `technical_06_natural`. El informe JSON conserva los textos necesarios para revisar qué afirmaciones añadió el modelo. Context Precision es precisión media de ranking; un 1,000 no significa necesariamente que todos los fragmentos recuperados sean relevantes.

No se mezclaron los resultados de 20B, del piloto de siete casos ni de los intentos con ejemplos few-shot con esta corrida de cierre. No afirmar que la calidad global de TechFixAI sea 86,4 %, 96 % o 95,2 %: son medias de métricas específicas sobre 25 casos puntuables y el perfil 120B declarado.

### Párrafo de resultados para el documento

La evaluación procesó 30 consultas sintéticas: 28 contestables según el corpus y dos controles fuera del dominio. Se recuperó contexto para 25 de las 28 consultas contestables, equivalente al 89,29 %. Sobre esos 25 casos, se obtuvieron medias de 0,864 en Faithfulness, 0,960 en Context Precision y 0,952 en Context Recall. Tres preguntas técnicas extensas quedaron sin contexto y se mantuvieron visibles en el informe, sin asignarles puntuaciones ficticias. Los dos controles no recuperaron información. La corrida finalizó sin errores operativos pendientes después de reanudar una evaluación afectada por un límite temporal del proveedor. Estos resultados corresponden a los componentes evaluados con GPT-OSS 120B y no constituyen una medida global del chat ni una evaluación completa del modelo 20B del backend.

### Cómo mostrar los resultados

Abrir `.local/ragas/project-20261111T065531240946Z/report.md` en VS Code y pulsar Ctrl+Shift+V para visualizar las tablas. Capturar los modelos del perfil, la tabla de medias con sus denominadores y la tabla de estados por caso. El CSV contiene las mismas puntuaciones y el JSON conserva contexto, respuesta, diagnóstico y procedencia.

### Fuentes técnicas

- Ragas, métricas disponibles: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/
- Groq, salidas estructuradas: https://console.groq.com/docs/structured-outputs
- Groq, límites de uso: https://console.groq.com/docs/rate-limits

El caso `faq_warranty` también respondió «No tengo esa información» sin recuperar la sección de garantía esperada (Faithfulness 0,000 y Context Recall 0,600). Debe interpretarse como abstención con recuperación incompleta, no como prueba automática de invención. Ambos casos requieren revisar la selección de secciones FAQ en una tarea posterior.

Ubicaciones para capturas en VS Code (Ctrl+G): `rag_eval/metrics.py`, líneas 5–13; `rag_eval/runtime.py`, funciones `prepare_case` y `generate_case`; `rag_eval/evaluate_project.py`, aproximadamente líneas 98–126 para el perfil y líneas 146–170 para las métricas. Los resultados y el texto final están en esta guía desde «Resultados de la corrida de cierre».

Reanudación verificada después de cerrar la corrida, con red restringida: los 30 casos se omitieron como completados, la salida fue 0 y se conservaron las 75 puntuaciones válidas sin nuevas peticiones. El estado previo al reintento temporal permanece en los archivos `*-before-resume`.
