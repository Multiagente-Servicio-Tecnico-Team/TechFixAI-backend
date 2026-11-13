"""BLEU de corpus y ROUGE Unicode, sin modelos ni llamadas de red."""
from __future__ import annotations

import importlib.metadata
import re
import unicodedata

ROUGE_TYPES = ("rouge1", "rouge2", "rougeL")


class SpanishTokenizer:
    """Conserva tildes, ñ, identificadores y códigos hexadecimales completos."""

    def tokenize(self, text):
        normalized = unicodedata.normalize("NFC", text).casefold()
        return re.findall(r"0x[0-9a-f]+|[^\W_]+(?:_[^\W_]+)*", normalized, flags=re.UNICODE)


def text_profile():
    return {
        "bleu": {"implementation": "sacrebleu.metrics.BLEU", "tokenize": "13a",
                 "lowercase": True, "smooth_method": "exp", "effective_order": False,
                 "max_ngram_orders": [1, 2, 3, 4], "aggregation": "corpus", "scale": "0..100"},
        "rouge": {"implementation": "rouge_score.rouge_scorer.RougeScorer",
                  "variants": list(ROUGE_TYPES), "tokenizer": "SpanishTokenizer_unicode_NFC_casefold_v1",
                  "use_stemmer": False, "aggregation": "macro_mean_per_case_f1", "scale": "0..1"},
        "versions": {n: importlib.metadata.version(n) for n in ("sacrebleu", "rouge-score")},
    }


def score_rouge(reference, response):
    from rouge_score.rouge_scorer import RougeScorer
    scorer = RougeScorer(ROUGE_TYPES, use_stemmer=False, tokenizer=SpanishTokenizer())
    scores = scorer.score(reference, response)
    return {name: {"precision": value.precision, "recall": value.recall, "f1": value.fmeasure}
            for name, value in scores.items()}


def corpus_bleu(rows):
    from sacrebleu.metrics import BLEU
    eligible = [r for r in rows if r["answerable"] and isinstance(r.get("response"), str)
                and r["response"].strip() and r.get("reference", "").strip()]
    results = {}
    for order in range(1, 5):
        scorer = BLEU(tokenize="13a", lowercase=True, smooth_method="exp",
                      max_ngram_order=order, effective_order=False)
        score = scorer.corpus_score([r["response"] for r in eligible], [[r["reference"] for r in eligible]]) if eligible else None
        results[f"bleu{order}"] = {
            "value": score.score if score else None, "evaluated": len(eligible),
            "signature": str(scorer.get_signature()) if score else None,
            "brevity_penalty": score.bp if score else None,
            "system_length": score.sys_len if score else None,
            "reference_length": score.ref_len if score else None,
        }
    return results
