# 34. Integración de Ragas para evaluar componentes RAG

## Objetivo y alcance

Dejar una evaluación reproducible en el repositorio que ejecute los componentes reales de recuperación/diagnóstico técnico jerárquico y recuperación/respuesta FAQ compartida. No incluye HTTP, autenticación, persistencia, cotizaciones, comparación de topologías ni calidad global del chat.

## Implementación

1. Dataset de 30 consultas sintéticas: dos formulaciones de los diez casos técnicos del manual, ocho FAQ y dos controles ajenos al corpus.
2. Referencias extraídas de las fuentes locales con rutas, anclas y hashes, verificadas antes de ejecutar. Registrar que falta revisión humana independiente.
3. Reutilizar las funciones actuales de recuperación y generación; el transporte de evaluación adapta el SDK compatible de Groq. No reescribir reglas de negocio ni cambiar el ranking para favorecer las preguntas.
4. Aplicar Faithfulness, ContextPrecision y ContextRecall de Ragas 0.4.3. Configurar JSON Schema estricto para el juez y límites explícitos de salida. Reintentar únicamente errores transitorios, con límites de intentos y espera.
5. Capturar el contexto exacto entregado al generador, sin recortes para elevar puntuaciones. Mantener preguntas sin contexto como hallazgos; no asignarles puntuaciones inventadas.
6. Exportar JSON, CSV y Markdown con estados, número de puntuaciones válidas, media y desviación poblacional por métrica. Registrar configuración, hashes de código/corpus/dataset, versión de dependencias y commit.
7. Usar caché local y reanudación compatible para no repetir peticiones exitosas. Rechazar reanudación si cambian fuentes, configuración o versiones.
8. Mantener los artefactos y caché en `.local/ragas/`, separados de las trazas operativas. Desactivar tracing y conexión DB solo en el proceso de evaluación.
9. No incluir mensajes reales de clientes, claves ni texto de excepciones. Los errores contienen únicamente clase, estado HTTP y código de máquina allowlisted.

## Validación y cierre

- Dry-run local de los 30 casos sin clave de API ni llamadas de red.
- Pruebas aisladas de formato estricto, caché, referencias, agregación sin valores ficticios y redacción segura de errores.
- Ejecución real autorizada de todos los casos; informar resultados válidos y cualquier fallo, sin considerar ausencias de contexto como errores del evaluador.
- Validación de reanudación y consistencia de dependencias.
- Actualizar guía, mapa de funcionalidades y memoria con evidencia y límites reales.

## Limitaciones metodológicas

El mismo modelo genera y juzga. Las FAQ contienen datos demostrativos según su propia fuente. Las referencias extraídas no equivalen a validación humana independiente. No se calcula Response Relevancy porque la configuración elegida no añade un proveedor/modelo de embeddings. El piloto anterior de siete casos utilizaba un prompt distinto y se conserva solo como evidencia histórica; no es una comparación controlada.
Perfil de cierre autorizado: --model openai/gpt-oss-120b para generación y juicio en la evaluación, sin modificar GROQ_MODEL del backend. Los prompts conservan las instrucciones y fórmulas originales de Ragas y omiten sus ejemplos few-shot para reducir consumo; se registra el perfil en metadatos. No mezclar sus resultados con perfiles anteriores ni atribuirlos al modelo 20B configurado en el backend.

