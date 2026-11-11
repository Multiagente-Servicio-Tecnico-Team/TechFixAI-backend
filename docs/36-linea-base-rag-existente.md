# 36. Evaluación del RAG existente antes de mejoras

## Decisión y alcance

El usuario pidió evaluar lo que ya tiene antes de mejorar el RAG. Se mantuvo intacto todo `app/`, incluido `app/rag/`. La propuesta de la tarea 35 no se usa en estas pruebas y queda como trabajo futuro.

Se evalúan la recuperación y el diagnóstico técnico jerárquico y la FAQ compartida, reutilizando sus funciones originales. No es una prueba del chat HTTP completo, ni una comparación de los tres grafos. No se escribieron datos de negocio ni se modificó el despliegue.

## Perfil de generación y juicio

- Generador: `openai/gpt-oss-20b` configurado en el proyecto, creado por su fábrica `create_model` y cliente ChatGroq.
- Juez: `openai/gpt-oss-120b` con Ragas 0.4.3, JSON Schema estricto y el perfil de prompts sin ejemplos genéricos ya documentado.
- Se eliminó del camino de generación nativo el límite de salida y el esfuerzo bajo impuestos por el puente anterior. Se utilizan los valores por defecto de la fábrica. El SDK normaliza la temperatura configurada 0 a 1e-8; la prueba verifica que no la sobrescribimos.
- `langchain-groq` 1.1.3 y `groq` 0.37.1 coinciden con las versiones del cliente del entorno backend. El resto de las versiones del entorno de evaluación se registra en metadatos; no se afirma identidad completa de entornos.
- La base de datos y el tracing remoto se desactivan en este proceso. El marcador de Settings solo satisface la validación de la fábrica, que crea el LLM; no se utiliza como conexión DB.

## Ejecución real y cuota

La prueba inicial de dos casos técnicos/FAQ terminó correctamente en `.local/ragas/project-20261111T081539787992Z/`.

La corrida principal del dataset original se guardó en `.local/ragas/project-20261111T081747383016Z/`. Se evaluaron nueve respuestas de 20B con las tres métricas y se conservaron tres preguntas técnicas sin contexto. Al intentar `technical_07_short`, Groq devolvió HTTP 429 por cuota diaria de tokens de 20B. La ejecución se detuvo sin sustituir el modelo y quedó lista para reanudar.

No se presenta la generación del dataset como completada. Los nueve casos puntuados de fidelidad corresponden a las primeras consultas técnicas procesadas; no representan todos los temas ni las FAQ.

## Recuperación completa con juicios en caché

Las métricas Context Precision y Context Recall usan pregunta, referencia y contexto, no la respuesta del generador. Para completar su informe se comprobaron los 30 contextos actuales contra los del benchmark anterior y se verificaron los hashes de las fuentes y el dataset. Luego Ragas recalculó ambas métricas usando exclusivamente los juicios 120B existentes en caché, con cliente que prohíbe llamadas nuevas.

Evidencia consolidada: `.local/ragas/baseline-current-20261111T082447298366Z/`, archivos `results.json`, `results.csv` y `report.md`. Metadatos y filas identifican los informes de origen. No se copiaron respuestas generadas por 120B a la evaluación de 20B, ni se inventaron valores faltantes. No se hicieron nuevas llamadas a proveedores para este informe de recuperación.

| Métrica | Media | Casos válidos | Estado |
| --- | ---: | ---: | --- |
| Faithfulness | 0,990 | 9 | Parcial: respuestas reales de 20B, juez 120B |
| Context Precision | 0,960 | 25 | Recuperación actual, juicios 120B idénticos en caché |
| Context Recall | 0,952 | 25 | Recuperación actual, juicios 120B idénticos en caché |

Hay 28 preguntas contestables: 25 recuperan contexto y 3 no. Los dos controles fuera del corpus no recuperan información. De los 25 casos con contexto, nueve tienen fidelidad calculada y 16 quedan pendientes de generación/evaluación en la corrida principal (uno alcanzó la cuota y quince aún no fueron procesados). El informe conserva ese estado parcial: no significa que haya cero errores o que se haya validado el chat completo.

La fidelidad 0,990 no se compara directamente con la media del perfil anterior 120B: cambiaron el generador, su transporte y el subconjunto puntuado. No demuestra una mejora del RAG; la recuperación no se modificó.

## Comandos

Evaluar el modelo configurado con su fábrica y un juez distinto:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --generator-transport backend --judge-model openai/gpt-oss-120b
```

Reanudar cuando 20B tenga cuota, manteniendo código, dataset y configuración:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --generator-transport backend --judge-model openai/gpt-oss-120b --resume .local/ragas/project-20261111T081747383016Z
```

Reproducir el informe completo de recuperación sin red:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_current_retrieval --generation-run .local/ragas/project-20261111T081747383016Z
```

## Validación

14 pruebas aisladas aprobadas: nueve del evaluador y cinco del transporte nativo. Verifican caché, parámetros originales del SDK, conservación del método JSON mode, aislamiento de DB, detección segura de cuota de Groq y presentación correcta de generador/juez distintos. No llaman a proveedores.

El manifiesto de producción y el contexto fueron verificados antes de reutilizar la evidencia. El evaluador anterior se archivó en `.local/ragas/evaluator-before-36/`; sus resultados no se sobrescribieron. Las versiones añadidas afectan únicamente a `.venv-ragas`. La suite general y sus cinco errores de fixture documentados en la tarea 34 no se reejecutaron porque no cambió código de app/.

## Texto para el documento

Se estableció una línea base del RAG existente sin modificar su implementación. Las respuestas se generaron mediante la fábrica de modelos del proyecto con GPT-OSS 20B y se evaluaron con GPT-OSS 120B como juez. La cuota diaria del generador permitió puntuar nueve respuestas antes de detener la corrida. Sobre ese subconjunto, Faithfulness obtuvo una media de 0,990. Para la recuperación, se validaron los contextos actuales y se reutilizaron juicios idénticos en caché: Context Precision y Context Recall obtuvieron medias de 0,960 y 0,952 sobre 25 casos. Tres de las 28 consultas contestables no recuperaron contexto. Estos resultados se presentan con sus denominadores y procedencia; la generación restante se mantiene pendiente de cuota y las mejoras se consideran en una etapa posterior.
## Revisión de aislamiento previa al commit

Se verificó que no existen cambios pendientes en `app/`, `requirements.txt`, `requirements-checkpoint.txt`, `pytest.ini` ni comandos de arranque del backend. `app/` no importa `rag_eval`. Las dependencias de evaluación permanecen en el pyproject y lock de esa carpeta, sin incorporarse a los requisitos principales.

Se reprodujo un riesgo de colección sin Ragas: `test_native_ragas_provider.py` importaba indirectamente la dependencia opcional. Se añadió `pytest.importorskip` antes de esos imports y se explicitó el mismo comportamiento en las pruebas del evaluador. La simulación sin Ragas terminó con 18 pruebas aprobadas y dos módulos omitidos. Se añadió `.venv-ragas/` al `.gitignore` principal, además de las exclusiones existentes de .env, .local y resultados de evaluación.

Suite aislada del backend tras la revisión: 582 aprobadas, 5 omitidas y 5 errores de la fixture `tests/integration/test_pattern_api.py` por `conversation_owners_repository`; no se modificó esa fixture ni la API. Estos errores son ajenos a las nuevas pruebas y pueden bloquear cualquier pipeline que exija suite completa verde.

Los archivos nuevos revisados no mostraron coincidencias de claves literales o URLs con credenciales en el escaneo local. Los resultados detallados y cachés permanecen en .local y no se incluyen en Git. El historial de documentación conserva resúmenes, sin claves.

No hay configuración de Render/Docker/workflow de despliegue versionada que permita verificar Root Directory, Build Command, Start Command ni rama de autodespliegue. Con instalación desde requirements.txt raíz y arranque app.main, estos cambios no añaden dependencias ni imports al servicio. Un commit local no publica cambios; el efecto de un push depende de la configuración externa. No se hizo commit, push ni deploy durante esta revisión.

Los archivos del quickstart `rag.py` y `evals.py` son ejemplos históricos, no necesarios para ejecutar el evaluador actual. Conviene excluirlos del commit funcional: el ejemplo genérico exporta trazas con consultas/respuestas y no forma parte de la política de trazas del proyecto. La propuesta 35 puede versionarse en un commit separado, identificada expresamente como no aplicada.
