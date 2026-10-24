"""Questions beyond school science, for checking the answer scorer.

The answer scorer (answer_scorer.py) was trained on SciQ, so its TF-IDF
vocabulary is school science; on security or business text about two thirds
of the words fall outside it. MMLU (Hendrycks et al. 2021, MIT licence) has
four-option questions in university subjects. In the app the scorer always
reads an answer against source text, so each MMLU question gets a support
passage: the lead of the Wikipedia article that a search for the question
and its answer finds (CC BY-SA; fetched once and cached, never committed).

Rows come out in SciQ's shape, so features/answer_features.expand_candidates
and the training code take them unchanged. The train/test split is by a hash
of the question, so a question never sits in both.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from . import config

SUBJECTS = ('computer_security', 'college_computer_science', 'machine_learning', 'business_ethics',
            'management', 'marketing', 'professional_accounting')
RAW = config.REPO_ROOT / 'datasets' / 'raw' / 'MMLU'
CACHE = RAW / 'wiki_support.json'
TEST_SHARE = 0.5
MIN_SUPPORT_CHARS = 80
WIKI_API = 'https://en.wikipedia.org/w/api.php'
USER_AGENT = 'StudyFlow-FYP/1.0 (university final-year project; answer-scorer evaluation)'


def load(subjects=SUBJECTS) -> pd.DataFrame:
    """The MMLU test questions of these subjects, as downloaded parquet files."""
    frames = []
    for s in subjects:
        df = pd.read_parquet(RAW / f'{s}.parquet')
        frames.append(df.assign(subject=s))
    return pd.concat(frames, ignore_index=True)


def split_of(question: str) -> str:
    h = int(hashlib.sha1(question.encode('utf-8')).hexdigest(), 16) % 1000
    return 'test' if h < TEST_SHARE * 1000 else 'train'


def to_sciq_shape(mmlu: pd.DataFrame) -> pd.DataFrame:
    """question, correct_answer, distractor1-3, plus subject and split."""
    rows = []
    for r in mmlu.itertuples(index=False):
        choices = [str(c) for c in r.choices]
        right = choices[int(r.answer)]
        wrong = [c for i, c in enumerate(choices) if i != int(r.answer)][:3]
        if len(wrong) < 3:
            continue
        rows.append({'question': str(r.question), 'correct_answer': right, 'distractor1': wrong[0],
                     'distractor2': wrong[1], 'distractor3': wrong[2], 'subject': r.subject,
                     'split': split_of(str(r.question))})
    return pd.DataFrame(rows)


def fetch_wikipedia(query: str) -> str:
    """The lead of the first Wikipedia article a search for `query` finds."""
    import requests
    params = {'action': 'query', 'generator': 'search', 'gsrsearch': query[:280], 'gsrlimit': 1,
              'prop': 'extracts', 'exintro': 1, 'explaintext': 1, 'format': 'json'}
    resp = requests.get(WIKI_API, params=params, headers={'User-Agent': USER_AGENT}, timeout=20)
    resp.raise_for_status()
    pages = (resp.json().get('query') or {}).get('pages') or {}
    return next((p.get('extract') or '' for p in pages.values()), '')


_FILLER = set("""which what who whom whose when where why how is are was were be been being the a an of
to in on for by with as at from that this these those following best most least true false
statement statements describes description describe following correct incorrect not except
does do did can could would should may might will shall it its their there here and or""".split())


def short_query(question: str, answer: str) -> str:
    """A shorter search for when the whole question finds nothing: the
    question's content words (up to 8) and the answer."""
    words = [w.strip('?.,:;()"\'') for w in str(question).split()]
    content = [w for w in words if w and w.lower() not in _FILLER][:8]
    return ' '.join(content + [str(answer)])


def with_support(df: pd.DataFrame, fetch: Callable[[str], str] = fetch_wikipedia,
                 cache: dict | None = None) -> pd.DataFrame:
    """Each row with a `support` passage; rows without a usable one are dropped.
    The whole question and its answer are searched first, a shorter query
    second. `cache` maps each search query to its passage."""
    cache = {} if cache is None else cache
    support = []
    for r in df.itertuples(index=False):
        found = ''
        for query in (f'{r.question} {r.correct_answer}', short_query(r.question, r.correct_answer)):
            if query not in cache:
                cache[query] = fetch(query) or ''
            if len(cache[query]) >= MIN_SUPPORT_CHARS:
                found = cache[query]
                break
        support.append(found)
    out = df.assign(support=support)
    return out[out.support.str.len() >= MIN_SUPPORT_CHARS].reset_index(drop=True)


def load_cache(path: Path = CACHE) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def save_cache(cache: dict, path: Path = CACHE) -> None:
    path.write_text(json.dumps(cache, ensure_ascii=False))
