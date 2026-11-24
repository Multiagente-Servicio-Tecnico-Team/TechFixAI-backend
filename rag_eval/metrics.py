"""Métricas Ragas estándar con instrucciones originales y sin ejemplos few-shot."""
from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness


def create_metrics(judge):
    faithfulness = Faithfulness(llm=judge)
    precision = ContextPrecision(llm=judge)
    recall = ContextRecall(llm=judge)
    # No se altera la fórmula, la instrucción ni el contexto evaluado.
    # Se quitan ejemplos ajenos al corpus para reducir el consumo de cuota.
    for prompt in (faithfulness.statement_generator_prompt, faithfulness.nli_statement_prompt, precision.prompt, recall.prompt):
        prompt.examples = []
    return {"faithfulness": faithfulness, "context_precision": precision, "context_recall": recall}