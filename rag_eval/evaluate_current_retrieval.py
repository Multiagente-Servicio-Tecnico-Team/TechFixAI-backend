"""Informe del RAG existente: recuperación completa en caché y generación 20B disponible."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from rag_eval.evaluate_project import ROOT, BASE, isolate_process, load_dataset, source_manifest


def local_run(path):
    resolved=path.resolve()
    if not resolved.is_relative_to((ROOT/'.local/ragas').resolve()):
        raise ValueError('La evidencia debe estar dentro de .local/ragas')
    return resolved


def verify_unchanged_sources(evidence):
    for name,digest in evidence['metadata']['source_sha256'].items():
        if name.startswith('app/') and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Cambió una fuente del proyecto: no reutilizar esta evidencia')


async def main():
    isolate_process()
    from rag_eval.metrics import create_metrics
    from rag_eval.providers import CompletionStore, StrictGroqJudge
    from rag_eval.reporting import save_report
    from rag_eval.runtime import prepare_case
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation-run',type=Path,required=True)
    parser.add_argument('--retrieval-source',type=Path,default=ROOT/'.local/ragas/project-20261111T065531240946Z')
    args=parser.parse_args()
    native_dir=local_run(args.generation_run)
    retrieval_dir=local_run(args.retrieval_source)
    native=json.loads((native_dir/'results.json').read_text(encoding='utf-8'))
    previous=json.loads((retrieval_dir/'results.json').read_text(encoding='utf-8'))
    if native['metadata'].get('generator_transport')!='backend' or not native['metadata']['model_matches_backend']:
        raise ValueError('Se requiere evidencia generada por la fábrica real del backend')
    verify_unchanged_sources(native)
    verify_unchanged_sources(previous)
    _,samples,dataset_hash=load_dataset(BASE/'dataset_project.json')
    if any(d['metadata']['dataset_sha256']!=dataset_hash for d in (native,previous)):
        raise ValueError('Los datasets no coinciden')
    if native['metadata']['judge_model']!=previous['metadata']['judge_model'] or native['metadata']['metric_prompt_profile']!=previous['metadata']['metric_prompt_profile']:
        raise ValueError('Los perfiles de juicio no coinciden')
    prepared={s['id']:prepare_case(s) for s in samples}
    previous_rows={r['id']:r for r in previous['results']}
    native_rows={r['id']:r for r in native['results']}
    for sample in samples:
        if prepared[sample['id']]['contexts']!=previous_rows[sample['id']]['retrieved_contexts']:
            raise ValueError('El contexto actual difiere del contexto de los juicios en caché')
    async def no_network(**kwargs):
        raise RuntimeError('Falta un juicio en caché; se prohíben llamadas nuevas en este informe')
    offline_client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=no_network)))
    store=CompletionStore(ROOT/'.local/ragas/cache-v2')
    judge=StrictGroqJudge(offline_client,native['metadata']['judge_model'],store)
    scorers=create_metrics(judge)
    rows=[]
    for sample in samples:
        old=previous_rows[sample['id']]
        generated=native_rows.get(sample['id'],{})
        row={**old,'response':generated.get('response'),'diagnosis':generated.get('diagnosis'),'faithfulness':generated.get('faithfulness'), 'failed_metrics':[], 'generation_evidence':native_dir.relative_to(ROOT).as_posix() if generated else None}
        if row['context_count'] and sample['answerable']:
            row['status']='ok' if row['faithfulness'] is not None else 'quota_exhausted' if generated.get('status')=='quota_exhausted' else 'generation_pending'
            for metric_name in ('context_precision','context_recall'):
                value=float((await scorers[metric_name].ascore(user_input=sample['user_input'],reference=sample['reference'],retrieved_contexts=prepared[sample['id']]['contexts'])).value)
                if abs(value-old[metric_name])>1e-9:
                    raise ValueError('Los juicios en caché no reproducen la puntuación previa')
                row[metric_name]=value
        else:
            row['status']='no_context' if sample['answerable'] else 'expected_abstention'
        rows.append(row)
    if store.calls!=0:
        raise RuntimeError('Se detectó un intento de llamada fuera de la caché')
    out=ROOT/'.local/ragas'/('baseline-current-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    metadata={**native['metadata'],'scope':'existing_rag_retrieval_complete_generation_partial','completion_state':'partial_due_20b_daily_quota','source_runs':{'native_generation':native_dir.relative_to(ROOT).as_posix(),'retrieval_context_validation':retrieval_dir.relative_to(ROOT).as_posix()},'retrieval_judgments_from_cache':True,'new_provider_calls':0,'cache_hits_this_report':store.hits,'candidate_used':False,'report_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    metadata['native_run_fingerprint']=metadata.pop('fingerprint')
    metadata['fingerprint']=hashlib.sha256(json.dumps({'sources':source_manifest(),'native_evidence':hashlib.sha256((native_dir/'results.json').read_bytes()).hexdigest(),'retrieval_evidence':hashlib.sha256((retrieval_dir/'results.json').read_bytes()).hexdigest(),'script':metadata['report_script_sha256']},sort_keys=True).encode()).hexdigest()
    summary=save_report(out,rows,metadata)
    note='# Línea base del RAG existente: generación parcial\n\nRecuperación evaluada sobre los 30 casos; fidelidad calculada solo para las respuestas disponibles de 20B. La cuota diaria impidió completar la generación. Los juicios de recuperación 120B se reutilizaron desde caché después de verificar fuentes, preguntas y contextos idénticos. No se generaron respuestas faltantes ni se incorporó la propuesta experimental.\n\n'
    report=out/'report.md'
    report.write_text(note+report.read_text(encoding='utf-8'),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print('Nuevas llamadas a proveedores: 0')
    print('Informe:',out)

if __name__=='__main__':
    try: asyncio.run(main())
    except Exception as error:
        print('No se pudo completar el informe. Tipo:',type(error).__name__)
        raise SystemExit(1)