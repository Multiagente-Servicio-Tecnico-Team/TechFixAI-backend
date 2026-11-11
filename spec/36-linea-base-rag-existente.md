# 36. Línea base del RAG existente con generador del backend

El usuario priorizó evaluar lo implementado antes de proponer mejoras. No modificar app/, ni activar la propuesta de la tarea 35, ni cambiar preguntas o referencias.

- Generar mediante `app.adapters.llm.model_factory.create_model` y las funciones originales de diagnóstico/FAQ. Mantener los parámetros que solicita el backend, sin forzar razonamiento bajo ni límite de salida del adaptador anterior.
- Usar 20B configurado y 120B como juez Ragas, identificando roles por separado.
- Instalar únicamente los clientes compatibles del backend en el entorno de evaluación; no modificar su entorno ni `.env`.
- Mantener aislamiento de BD/tracing. La fábrica exige una URL no vacía para validación, pero la evaluación no crea conexión: se usa un marcador solo en Settings y DATABASE_URL sigue vacío en el proceso.
- Conservar el dataset original de 30 casos y todos los fallos de recuperación.
- Ante cuota diaria, parar generación, guardar los resultados y dejar reanudación exacta. No sustituir por respuestas de otro modelo ni afirmar que la corrida está completa.
- Para métricas de recuperación independientes del generador, permitir juicios en caché solo con fuentes, contextos, referencias, modelo juez y perfil idénticos; validar que reproduzcan las puntuaciones y prohibir llamadas nuevas en ese informe.
- Informar denominadores, procedencia y el estado parcial de Faithfulness. Las mejoras se consideran después de esta línea base.
Aislamiento para versionado: las pruebas que requieren Ragas deben omitirse si la dependencia opcional no está instalada; no añadirla a requirements.txt del backend y excluir explícitamente .venv-ragas del repositorio.
