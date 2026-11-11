"""Compara recuperación actual y propuesta; sin LLM ni cambios en app/rag/."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from rag_eval.evaluate_project import BASE, ROOT, isolate_process, load_dataset, source_manifest


def app_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'app/rag').rglob('*.py'))}


def source_hit(sample, prepared):
    if not sample['answerable']:
        return None
    if sample['route']=='technical':
        return sample['expected_source_id'] in prepared['source_ids']
    return sample['reference_anchor'] in prepared['context']


def main():
    isolate_process()
    os.environ['RAG_RETRIEVAL_MODE']='lexical'
    from rag_eval.runtime import prepare_case
    from rag_eval.retrieval_candidate import prepare_candidate_case
    before_hashes=app_hashes()
    _,samples,dataset_hash=load_dataset(BASE/'dataset_project.json')
    rows=[]
    for sample in samples:
        current=prepare_case(sample)
        candidate=prepare_candidate_case(sample)
        row={'id':sample['id'],'route':sample['route'],'answerable':sample['answerable'],'user_input':sample['user_input'],
             'candidate_retrieval_query':candidate['retrieval_query'],
             'current':{'context_count':len(current['contexts']),'expected_source_hit':source_hit(sample,current)},
             'candidate':{'context_count':len(candidate['contexts']),'expected_source_hit':source_hit(sample,candidate),'selected_sections':candidate.get('selected_sections',[])}}
        rows.append(row)
        print(f"{sample['id']}: actual={row['current']['context_count']} / propuesta={row['candidate']['context_count']}; fuente actual={row['current']['expected_source_hit']} / propuesta={row['candidate']['expected_source_hit']}")
    if before_hashes!=app_hashes():
        raise RuntimeError('Se detectó un cambio inesperado en las fuentes de app/rag')
    summary={}
    for profile in ('current','candidate'):
        summary[profile]={'answerable_with_context':sum(r['answerable'] and r[profile]['context_count']>0 for r in rows),
                          'expected_source_found':sum(r[profile]['expected_source_hit'] is True for r in rows),
                          'controls_without_context':sum(not r['answerable'] and r[profile]['context_count']==0 for r in rows)}
    summary['regressions']=[r['id'] for r in rows if r['current']['expected_source_hit'] is True and r['candidate']['expected_source_hit'] is not True]
    directory=ROOT/'.local/ragas'/('retrieval-proposal-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(parents=True)
    payload={'scope':'offline_candidate_not_applied_to_app','retrieval_mode':'lexical','dataset_sha256':dataset_hash,'app_rag_sha256':before_hashes,'production_source_sha256':source_manifest(),'candidate_source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('rag_eval/retrieval_candidate.py','rag_eval/compare_retrieval.py')},'summary':summary,'results':rows}
    (directory/'comparison.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Propuesta local de recuperación (no aplicada)', '', '| Indicador | Actual | Propuesta |', '| --- | ---: | ---: |']
    for field in ('answerable_with_context','expected_source_found','controls_without_context'):
        lines.append(f"| {field} | {summary['current'][field]} | {summary['candidate'][field]} |")
    lines += ['', '| Caso | Contextos actuales | Contextos propuesta | Fuente actual | Fuente propuesta |','| --- | ---: | ---: | --- | --- |']
    for r in rows:
        lines.append(f"| {r['id']} | {r['current']['context_count']} | {r['candidate']['context_count']} | {r['current']['expected_source_hit']} | {r['candidate']['expected_source_hit']} |")
    lines += ['', 'No se ejecutó Groq ni Ragas. No son nuevas puntuaciones de fidelidad, precisión o cobertura de Ragas. No se modificaron los archivos de app/rag ni las preguntas originales del dataset.', 'Las referencias y casos forman parte del mismo conjunto piloto: estos resultados no prueban generalización fuera de él.']
    (directory/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True,indent=2))
    print('Evidencia:',directory)

if __name__=='__main__':
    main()