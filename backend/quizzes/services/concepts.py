"""Turning a mistake bank into named concepts.

The grouping is ml_pipeline.weak_concepts (TF-IDF + clustering, no model);
naming a group is the one place a language model earns its keep — "mobile,
homeless, young" becomes "Phones and the safety of homeless youth". Names
are cached for a day per exact group, so a page reload costs no LLM call.
"""
import hashlib
import logging

from django.core.cache import cache

from ml_pipeline.weak_concepts import cluster_questions, top_terms
from notebooks.services.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)

LABEL_TTL = 60 * 60 * 24


def concepts_for(questions) -> list[dict]:
    """`questions` are Question rows (any order). Returns concepts biggest
    first: {key, label, question_ids, count, sample}."""
    questions = list(questions)
    texts = [f'{q.question_text} {q.correct_answer} {q.source_excerpt or ""}' for q in questions]
    plain = [q.question_text for q in questions]
    out = []
    for cluster in cluster_questions(texts):
        members = [questions[i] for i in cluster.indices]
        ids = sorted(q.id for q in members)
        key = hashlib.sha1(','.join(map(str, ids)).encode()).hexdigest()[:12]
        out.append({
            'key': key,
            'label': _label(key, [q.question_text for q in members],
                            top_terms(plain, cluster.indices)),
            'question_ids': ids,
            'count': len(ids),
            'sample': [q.question_text for q in members[:3]],
        })
    return out


def _label(key: str, question_texts: list[str], fallback_terms: list[str]) -> str:
    cache_key = f'concept-label:{key}'
    cached = cache.get(cache_key)
    if cached:
        return cached
    label = _name_with_llm(question_texts) or ', '.join(fallback_terms) or question_texts[0][:60]
    cache.set(cache_key, label, LABEL_TTL)
    return label


def _name_with_llm(question_texts: list[str]) -> str:
    listed = '\n'.join(f'- {t}' for t in question_texts[:8])
    prompt = f"""These quiz questions all test one concept. Name that concept in 2 to 5 words,
in the same language as the questions — a noun phrase, no quotes, no trailing period.

{listed}

Return ONLY valid JSON: {{"label": "..."}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
        label = str(data.get('label') or '').strip().strip('."\'')
        return label[:80]
    except Exception as exc:  # noqa: BLE001 — no provider, quota, bad JSON: all mean "use the terms"
        logger.info('Concept naming fell back to key terms: %s', exc)
        return ''
