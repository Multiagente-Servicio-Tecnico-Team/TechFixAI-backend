"""Genera evidencia local de presupuesto y fallo deliberado, sin servicios externos."""
import json
from pathlib import Path
from langgraph.graph import END, START, StateGraph
from app.agents.sales import DEMO_REQUEST, QuoteState, build_sales_graph
from app.tracing import invoke_traced


def main():
    path = Path(".local/acceptance-traces.jsonl")
    result, execution_id = invoke_traced(build_sales_graph(), {"request": DEMO_REQUEST}, path)
    Path(".local/quote-example.json").write_text(json.dumps(result["quote"], ensure_ascii=False, indent=2), encoding="utf-8")

    def failure(state):
        raise RuntimeError("password=synthetic-secret-not-for-logs")

    builder = StateGraph(QuoteState)
    builder.add_node("failure_probe", failure)
    builder.add_edge(START, "failure_probe")
    builder.add_edge("failure_probe", END)
    try:
        invoke_traced(builder.compile(), {"request": {}}, path)
    except RuntimeError:
        pass
    content = path.read_text(encoding="utf-8")
    assert "synthetic-secret" not in content
    assert any(row["event"] == "error" for row in map(json.loads, content.splitlines()))
    print("Presupuesto y fallo controlado registrados en .local; secreto excluido.")


if __name__ == "__main__":
    main()
