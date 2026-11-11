import asyncio
import json
from pathlib import Path
from openai import AsyncOpenAI
from ragas.metrics.collections import Faithfulness
from app.settings import load_settings
from rag_eval.providers import ENDPOINT, CompletionStore, StrictGroqJudge, safe_error

async def main():
    s=load_settings()
    data=json.loads(Path('.local/ragas/20261111T060317567694Z/results.json').read_text(encoding='utf-8'))
    row=next(r for r in data['results'] if r['id']=='disk_usage')
    async with AsyncOpenAI(api_key=s.groq_api_key,base_url=ENDPOINT,max_retries=0,timeout=60) as client:
        judge=StrictGroqJudge(client,s.groq_model,CompletionStore('.local/ragas/cache-v2'))
        score=await Faithfulness(llm=judge).ascore(user_input=row['user_input'],response=row['response'],retrieved_contexts=row['retrieved_contexts'])
        print('Faithfulness del caso antes fallido:',score.value)
if __name__=='__main__':
    try: asyncio.run(main())
    except Exception as e: print(safe_error(e))