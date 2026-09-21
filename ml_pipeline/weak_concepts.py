"""Which concepts a student keeps missing.

Missed questions are grouped by what they are about, so "you got 12 wrong"
becomes "you are weak on the Calvin cycle and anaerobic respiration". No
language model: TF-IDF over words and character n-grams, which works for
Vietnamese as well as English, then agglomerative clustering on cosine
distance. The threshold was chosen in notebooks/05_weak_concepts.ipynb.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import hstack
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

# Cosine distance at which two questions stop counting as the same concept.
# Swept on the dev mistake bank (49 questions, notebook 05): 0.85 groups 41
# of them into 14 clusters and its largest (9) is one real concept — mobile
# phones and the safety of homeless youth; 0.8 splits that concept in three
# and drops Vietnamese pairs that share only the concept's two-syllable name;
# 0.9 fuses unrelated CityHelp questions.
DISTANCE_THRESHOLD = 0.85
MIN_CLUSTER_SIZE = 2

# Function words that would otherwise top a label ("the paper", "was the").
# English from scikit-learn; Vietnamese is a short hand list — no tokenizer.
_VI_STOP = {
    "là", "gì", "của", "nào", "trong", "theo", "và", "có", "được", "những", "các",
    "một", "này", "đó", "ở", "với", "cho", "khi", "để", "từ", "như", "thế", "nào",
    "vì", "sao", "hay", "không", "đúng", "sai", "bao", "nhiêu", "ai", "đâu",
}


@dataclass(frozen=True)
class Cluster:
    indices: list[int]          # positions in the input list, biggest cluster first


def _vectorise(texts: list[str]):
    """Words catch topical overlap; character n-grams catch inflection and
    diacritics (quang hợp / quang hợp's variants) without a tokenizer."""
    words = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True,
                            min_df=1, lowercase=True)
    chars = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                            min_df=1, lowercase=True)
    mat = hstack([words.fit_transform(texts), chars.fit_transform(texts)]).tocsr()
    # Row-normalise so cosine distance is 1 - dot product.
    norms = np.sqrt(mat.multiply(mat).sum(axis=1)).A1
    norms[norms == 0] = 1.0
    return mat.multiply(1.0 / norms[:, None]).tocsr()


def cluster_questions(texts: list[str], threshold: float = DISTANCE_THRESHOLD,
                      min_size: int = MIN_CLUSTER_SIZE) -> list[Cluster]:
    """Groups of at least `min_size` questions about the same thing."""
    if len(texts) < min_size:
        return []
    mat = _vectorise(texts)
    dense = mat.toarray()
    labels = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=threshold,
    ).fit_predict(dense)
    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(int(lab), []).append(i)
    clusters = [Cluster(sorted(ix)) for ix in groups.values() if len(ix) >= min_size]
    # Biggest first; ties by first member so the order is stable.
    clusters.sort(key=lambda c: (-len(c.indices), c.indices[0]))
    return clusters


def top_terms(texts: list[str], indices: list[int], k: int = 3) -> list[str]:
    """The words that set this cluster apart from the rest — a fallback label
    when no language model is around to name it."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, lowercase=True,
                          stop_words=list(ENGLISH_STOP_WORDS | _VI_STOP))
    mat = vec.fit_transform(texts)
    inside = np.asarray(mat[indices].mean(axis=0)).ravel()
    others = [i for i in range(len(texts)) if i not in set(indices)]
    outside = np.asarray(mat[others].mean(axis=0)).ravel() if others else np.zeros_like(inside)
    score = inside - outside
    terms = vec.get_feature_names_out()
    order = np.argsort(-score)
    picked: list[str] = []
    for j in order:
        term = terms[j]
        if score[j] <= 0:
            break
        # "mobile phones" beats "mobile": keep the more specific of an
        # overlapping pair, whichever scored first.
        overlap = next((p for p in picked if term in p or p in term), None)
        if overlap is not None:
            if len(term) > len(overlap):
                picked[picked.index(overlap)] = term
            continue
        picked.append(term)
        if len(picked) == k:
            break
    return picked
