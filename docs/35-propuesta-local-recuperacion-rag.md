# 35. Propuesta experimental de recuperación

## Estado

Propuesta local preparada y comprobada; no aplicada al RAG de TechFixAI. Por instrucción explícita del usuario, no se modificó ningún archivo de `app/rag/`. El chat y el evaluador canónico conservan el comportamiento anterior.

## Evidencia

`.local/ragas/retrieval-proposal-20261111T074724482960Z/comparison.json` y `report.md`.

Se utilizó el mismo dataset de 30 consultas, sin cambiar preguntas ni referencias. La comparación se ejecutó localmente en modo léxico, sin Groq, embeddings, modelos nuevos ni escrituras en BD. Los hashes de `app/rag/` permanecieron iguales; además, el manifiesto del benchmark previo siguió coincidiendo con las fuentes actuales.

| Indicador | RAG actual | Propuesta local |
| --- | ---: | ---: |
| Preguntas contestables con contexto | 25/28 | 28/28 |
| Preguntas contestables con fuente esperada presente | 23/28 | 28/28 |
| Controles sin recuperación | 2/2 | 2/2 |
| Fuentes esperadas perdidas respecto al actual | — | 0 |

La propuesta recuperó los casos técnicos 2, 3 y 4 formulados como preguntas extensas, y seleccionó las secciones de tarifas y garantía para sus respectivas FAQ. Estos conteos no equivalen a Faithfulness, Context Precision ni Context Recall de Ragas. Tampoco prueban generalización fuera del conjunto piloto.

## Archivos

- `rag_eval/retrieval_candidate.py`: preparación experimental de consultas y selección de secciones FAQ, reutilizando normalización, configuración y recuperación existentes.
- `rag_eval/compare_retrieval.py`: comparación reproducible entre el comportamiento actual y la propuesta; genera evidencia y comprueba integridad del código de app/rag.
- `tests/unit/rag/test_retrieval_candidate.py`: pruebas adicionales, incluidas preguntas que no estaban en el dataset.

La consulta preparada se conserva separada de `user_input`. La pregunta original permanece en el mensaje y la descripción del estado que recibiría el generador; no se modifica el dataset para hacer que el benchmark pase.

## Validación

20 pruebas aprobadas: 11 de la propuesta y 9 del evaluador existente. Se comprobaron formulaciones técnicas nuevas, código hexadecimal desconocido, conservación de negación y restricciones, prioridad de temas explícitos, varios temas FAQ con límite de fragmentos y abstención ante una petición de ayuda ajena al corpus.

```powershell
.\.venv-ragas\Scripts\python.exe -m rag_eval.compare_retrieval
.\.venv-ragas\Scripts\python.exe -m pytest -q tests/unit/rag/test_retrieval_candidate.py tests/unit/rag/test_ragas_evaluation.py
```

Compilación de los dos módulos experimentales correcta. La comparación de hashes confirmó que el RAG de producción y el evaluador original permanecen intactos. La consulta de PR no pudo completarse: gh no está instalado y el conector GitHub devolvió falta de acceso/nombre no resoluble; git fetch --all sí terminó correctamente.

## Texto para el documento

A partir de los fallos observados en la evaluación, se preparó una propuesta aislada de recuperación. Esta propuesta utiliza una consulta de búsqueda derivada de la pregunta original y prioriza los temas explícitos al seleccionar secciones de preguntas frecuentes. Reutiliza el recuperador existente y no modifica su ranking ni sus umbrales. En una comparación local sobre las mismas 30 consultas, las preguntas contestables con contexto pasaron de 25 a 28 y las fuentes esperadas encontradas pasaron de 23 a 28, manteniendo sin recuperación los dos controles fuera del dominio. Estos resultados corresponden a un experimento local; la propuesta no se incorporó al RAG del proyecto ni se volvió a puntuar con Ragas.

## Límites y siguiente etapa

La propuesta se desarrolló con conocimiento de los fallos del piloto; se necesitan más casos independientes y revisión humana. La comparación local no mide la calidad de las respuestas generadas. La selección de temas sigue siendo léxica y puede requerir mejoras para otras ambigüedades. Cualquier incorporación al runtime deberá revisarse por separado y contar con autorización para modificar app/rag. Hasta entonces no debe afirmarse que el RAG desplegado mejoró ni reemplazar las puntuaciones del benchmark anterior.
Actualización de alcance: el usuario priorizó medir el RAG existente antes de mejorar. Esta propuesta sigue sin aplicarse y se conserva solo como trabajo futuro. La línea base actual está en docs/36-linea-base-rag-existente.md.
