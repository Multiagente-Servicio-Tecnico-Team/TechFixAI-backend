# Evaluación Ragas de TechFixAI

Evalúa componentes RAG existentes en este repositorio. No ejecuta el chat HTTP, tickets, pagos, inventario ni escrituras PostgreSQL.

Para la evaluación actual con Ragas, BLEU y ROUGE usa `python -m rag_eval.baseline`. Los comandos completos y resultados están en [la guía 37](../docs/37-evaluacion-automatica-rag.md).

## Evaluador histórico de las tareas 34 y 36 (desde la raíz)

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --dry-run
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --model openai/gpt-oss-120b
```

La primera orden no usa red ni necesita clave. La segunda usa `GROQ_API_KEY` y `GROQ_MODEL` ya configurados en el proyecto. Se ha autorizado enviar a Groq las preguntas sintéticas y los fragmentos/referencias de manuales técnicos y FAQ; no utilizar conversaciones reales de clientes en este dataset.

Para una prueba breve:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --only technical_01_short faq_payments
```

## Reanudar y evitar cargos repetidos

Cada corrida crea `.local/ragas/project-<fecha UTC>/` con `results.json`, `results.csv` y `report.md`. Reanudar la misma configuración:

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.evaluate_project --model openai/gpt-oss-120b --resume .local/ragas/project-REEMPLAZAR
```

Al reanudar se omiten los casos ya completados y se conservan las métricas válidas de casos con errores. La caché local de respuestas usa el hash del modelo, parámetros y petición, sin claves; un cambio de petición obliga a evaluarla de nuevo. Se verifica que dataset, fuentes, código y versiones coincidan con la corrida. No modificar los resultados JSON a mano.

## Qué se evalúa

- Diagnóstico: `make_knowledge_retrieval_agent`, `MarkdownKnowledgeRetriever` y `make_technical_support_agent` del patrón jerárquico. Se evalúa el texto de diagnóstico provisional, no la cotización final.
- FAQ: `MarkdownFaqRetriever` y `answer_faq`, compartidas por el proyecto.
- Transporte: puente local con el SDK compatible OpenAI de Groq. Reutiliza los prompts y funciones de negocio existentes, pero no la orquestación completa ni la clase ChatGroq.
- Juez: Ragas 0.4.3 con Faithfulness, ContextPrecision y ContextRecall estándar; salida JSON Schema estricta, `reasoning_effort=low`, máximo 4096 tokens y reintentos limitados solo para errores transitorios. No se reemplazan las métricas ni se cambia el ranking para elevar resultados.

## Dataset y límites

`dataset_project.json` contiene 30 casos: dos formulaciones para los diez casos técnicos, ocho FAQ y dos controles fuera del corpus. Las referencias se extraen de los documentos; el loader verifica extractos y hashes. No hubo revisión humana independiente. La FAQ se declara demostrativa en su fuente: se mide fidelidad al corpus, no veracidad comercial.

Los casos contestables sin contexto permanecen visibles y sus métricas quedan nulas. Siempre informar cobertura y número de casos puntuables junto con las medias. El mismo modelo genera y juzga: existe sesgo y una puntuación alta no certifica verdad ni calidad integral del chat. Las métricas de recuperación se calculan aunque falle la generación, cuando hay contexto.

## Dependencias y pruebas

El entorno validado usa Python 3.13. Las versiones exactas están en `requirements-lock.txt` (UTF-8). Para recrearlo en Windows compatible:

```powershell
python -m venv .venv-ragas
.\.venv-ragas\Scripts\python.exe -m pip install -r rag_eval/requirements-lock.txt
.\.venv-ragas\Scripts\python.exe -m pip check
.\.venv-ragas\Scripts\python.exe -m pytest -q tests/unit/rag/test_ragas_evaluation.py
```

No es necesario activar el entorno. Las dependencias están separadas del backend. No desactivar controles de seguridad de Windows; la combinación validada incluye PyArrow 19.0.1, datasets 4.0.0 y langchain-community 0.3.31.

## Archivos históricos

`rag.py`, `evals.py` y `evals/` proceden del quickstart de Ragas: no son la integración con TechFixAI. `prueba_rag.py`, `dataset_techfix.json` y `evaluate_techfix.py` conservan el piloto inicial de siete casos con un prompt de prueba. Sus cifras no son directamente comparables con la evaluación de componentes reales. La documentación vigente y la evidencia están en `docs/34-evaluacion-rag-ragas.md`.

Response Relevancy no forma parte de esta configuración: requiere embeddings adicionales. El alcance elegido se completa con las tres métricas declaradas; no se presenta una relevancia semántica que no se haya calculado.
## Perfil utilizado y cuota

El backend conserva `openai/gpt-oss-20b`. Se agotó su cuota diaria durante la evaluación. Con autorización del usuario, la corrida de cierre utiliza `--model openai/gpt-oss-120b` para generación y juicio solo en el proceso de evaluación. El informe registra que el modelo evaluado no coincide con el configurado en el backend. No atribuir estas puntuaciones a 20B ni comparar directamente las cifras con el piloto anterior.

Para evaluar exactamente el modelo configurado en el backend, omitir `--model` cuando disponga de cuota. `--judge-model` permite declarar un juez distinto. Una cuota diaria agotada produce salida 2, guarda la evidencia y detiene nuevos intentos. No se cambia de modelo automáticamente.

Los prompts del juez conservan las instrucciones y fórmulas originales de las métricas Ragas, pero omiten los ejemplos few-shot ajenos al corpus para reducir consumo. Este perfil se registra en metadatos; no es idéntico al del piloto inicial. No se recortan las preguntas, respuestas o contextos reales evaluados.
## Propuesta de recuperación no aplicada

Para revisar el experimento local sin tocar app/rag ni usar Groq: ejecutar .\.venv-ragas\Scripts\python.exe -m rag_eval.compare_retrieval desde la raíz. La propuesta vive en retrieval_candidate.py y no es utilizada por evaluate_project.py ni por el servidor. Comparación y límites en docs/35-propuesta-local-recuperacion-rag.md.


## Evaluar lo que usa el proyecto (sin aplicar la propuesta)

Usar --generator-transport backend --judge-model openai/gpt-oss-120b con evaluate_project.py. Reutiliza create_model/ChatGroq y sus parámetros originales; no cambia app/. La corrida 20B es parcial por cuota diaria. Context Precision y Context Recall del RAG existente se verificaron con juicios idénticos en caché mediante evaluate_current_retrieval.py; no se mezclan respuestas de 120B. Comandos y resultados con denominadores en docs/36-linea-base-rag-existente.md.

## Evaluación automática con generación y puntuación separadas

El CLI `python -m rag_eval.baseline` amplía este evaluador sin cambiar los componentes del backend. Incluye `audit`, `prepare-embeddings`, `generate` (también reanuda) y `score --group text|ragas|all`. `score --group text` calcula BLEU/ROUGE localmente; `--cache-only` prohíbe llamadas nuevas al juez Ragas. Los resultados permanecen en `.local/ragas`.

Guía de instalación, comandos PowerShell, procedencia y resultados: [docs/37-evaluacion-automatica-rag.md](../docs/37-evaluacion-automatica-rag.md). Dataset y evaluadores históricos conservados; las respuestas 120B no se mezclan con la línea base del generador 20B.

