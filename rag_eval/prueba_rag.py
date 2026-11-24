import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import Faithfulness
from app.rag.retriever import retrieve_documents
from app.settings import load_settings


async def main():
    settings = load_settings()
    question = "pantalla azul 0x0000007B"

    # Recuperación real de los manuales de TechFixAI.
    passages = retrieve_documents(
        question,
        allowed_areas={"technical"},
        allowed_trust_levels={"verified_guide"},
        limit=3,
    )
    contexts = [passage.content for passage in passages]

    if not contexts:
        print("No se recuperaron fragmentos. Hay que revisar la búsqueda.")
        return

    async with AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
        max_retries=1,
        timeout=90,
    ) as client:
        # Generación de una respuesta usando exactamente esos fragmentos.
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente de soporte técnico. "
                        "Responde en español usando únicamente el contexto. "
                        "Distingue causas posibles de diagnósticos confirmados. "
                        "Si falta información, indícalo.\n\n"
                        "Contexto:\n" + "\n\n".join(contexts)
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        response = completion.choices[0].message.content or ""

        # Ragas evalúa si la respuesta está respaldada por el contexto.
        judge = llm_factory(
            settings.groq_model,
            provider="openai",
            client=client,
            temperature=0,
            max_tokens=8192,
        )
        metric = Faithfulness(llm=judge)
        score = await metric.ascore(
            user_input=question,
            response=response,
            retrieved_contexts=contexts,
        )

    result = {
        "user_input": question,
        "retrieved_contexts": contexts,
        "sources": [passage.source_id for passage in passages],
        "response": response,
        "faithfulness": score.value,
        "model": settings.groq_model,
        "retrieval_mode": settings.rag_retrieval_mode,
    }

    output = Path(__file__).parent / "resultado_prueba.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Respuesta:", response)
    print("Faithfulness:", score.value)
    print("Resultado guardado en:", output)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(
            "La prueba falló.",
            "Tipo:", type(error).__name__,
            "HTTP:", getattr(error, "status_code", "no disponible"),
        )
        raise SystemExit(1)
