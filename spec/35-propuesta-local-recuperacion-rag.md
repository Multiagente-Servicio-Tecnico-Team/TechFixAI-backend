# 35. Propuesta local de recuperación, sin modificar app/rag

## Restricción del usuario

No modificar todavía `app/rag/`. La propuesta permanece exclusivamente en `rag_eval/`, con pruebas aisladas bajo `tests/`. No se incorpora al servidor, al evaluador canónico ni a los agentes del proyecto.

## Objetivo

Investigar los tres casos técnicos sin contexto y las FAQ de tarifas/garantía con secciones insuficientes, manteniendo inalteradas las preguntas y referencias del dataset de 30 casos.

## Diseño experimental

- Preparar una consulta de búsqueda separada de la pregunta original: retirar vocabulario de formulación, conservar síntomas, negación e identificadores y buscar códigos hexadecimales explícitos.
- Reutilizar `rag_eval.runtime.prepare_case`, los retrievers y la normalización existentes. No implementar otro ranking, otro índice ni modificar umbrales.
- En FAQ reutilizar el mapa de temas existente, distinguir temas explícitos de contexto secundario y consultar cada sección mediante el recuperador común. Respetar el límite de fragmentos y cubrir primero los distintos temas solicitados.
- Preservar la pregunta original en el estado que recibiría el generador.
- Comparar actual/propuesta en modo léxico y sin LLM. Verificar hashes del código de app/rag antes y después.
- Registrar consultas preparadas, procedencia, fuente esperada y controles, sin convertir estas comprobaciones en puntuaciones Ragas.

## Criterios de revisión

Recuperar las fuentes esperadas de los casos problemáticos sin perder las que ya se recuperaban, conservar abstención en controles y comprobar formulaciones nuevas, identificadores desconocidos, negación y consultas multitema.

La aprobación de esta propuesta no está implícita: el usuario pidió no modificar todavía app/rag. Aplicación al runtime, nueva evaluación Ragas y revisión humana quedan para una etapa posterior.