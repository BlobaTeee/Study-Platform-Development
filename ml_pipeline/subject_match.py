"""Which notebook a newly uploaded document belongs in.

A document dropped on the notebooks page is compared with the documents in
each of the student's notebooks: TF-IDF over words and character n-grams,
the same representation as weak_concepts, so no model call is spent and
Vietnamese works as well as English. A notebook scores as its closest
document — a subject's notebook holds several topics, and a new lecture is
usually close to one of them rather than to their average.

Below `MATCH_THRESHOLD` no notebook is close enough and the document starts
a new one. The threshold is picked in notebooks/07_subject_matching.ipynb.
"""
from __future__ import annotations

from typing import Hashable

#: Read this much of each document: enough to say what it is about, and it
#: keeps a 130k-character paper from dominating the comparison's cost.
MAX_CHARS = 20000

#: Cosine similarity a notebook's closest document must reach to take the
#: new one. Chosen in 07_subject_matching.ipynb.
MATCH_THRESHOLD = 0.35


def _vectorise(texts: list[str]):
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import normalize

    words = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
                            lowercase=True, max_df=0.9 if len(texts) > 3 else 1.0)
    chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                            lowercase=True)
    return normalize(hstack([words.fit_transform(texts), chars.fit_transform(texts)]).tocsr())


def score_notebooks(text: str, notebooks: dict[Hashable, list[str]]) -> list[tuple[Hashable, float]]:
    """(notebook, score) for every notebook with at least one document,
    best first. A notebook's score is its closest document's similarity."""
    owners, docs = [], []
    for key, texts in notebooks.items():
        for doc in texts:
            if doc and doc.strip():
                owners.append(key)
                docs.append(doc[:MAX_CHARS])
    if not docs or not text.strip():
        return []
    mat = _vectorise([text[:MAX_CHARS]] + docs)
    sims = (mat[0] @ mat[1:].T).toarray().ravel()
    best: dict[Hashable, float] = {}
    for key, sim in zip(owners, sims):
        best[key] = max(best.get(key, 0.0), float(sim))
    return sorted(best.items(), key=lambda kv: -kv[1])


def best_notebook(text: str, notebooks: dict[Hashable, list[str]],
                  threshold: float | None = None) -> Hashable | None:
    """The notebook the document belongs in, or None to start a new one."""
    threshold = MATCH_THRESHOLD if threshold is None else threshold
    ranked = score_notebooks(text, notebooks)
    if not ranked or ranked[0][1] < threshold:
        return None
    return ranked[0][0]
