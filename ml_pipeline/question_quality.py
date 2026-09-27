"""Chấm chất lượng một câu hỏi trắc nghiệm sinh từ tài liệu của người học.

Phép kiểm ngây thơ — "đáp án có xuất hiện nguyên văn trong đoạn nguồn không" —
chấm sai cả hai chiều: câu hỏi dạng phủ định ("điều nào KHÔNG được nêu") có đáp
án cố tình không nằm trong nguồn, còn một câu hỏi hỏng vì *phương án nhiễu cũng
đúng* lại được cho là tốt vì đáp án của nó chép lại từ nguồn. Module này đo cái
đáng đo: tài liệu có khẳng định đáp án không, có nhiễu nào cũng đúng không, và
nhiễu có nhại lại đáp án không.

Không dùng model ngôn ngữ: so khớp bằng TF-IDF ký tự + từ, nên chạy được cho cả
tiếng Việt lẫn tiếng Anh, nhanh, và cho ra cùng một con số ở mọi lần chạy.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer

# Một mệnh đề được coi là "tài liệu có khẳng định" khi vượt ngưỡng này.
SUPPORTED = 0.45
# Nhiễu đạt tới mức này so với đoạn nguồn thì coi như cũng đúng.
RIVAL = 0.45
# Nhiễu giống đáp án tới mức này thì là nhại lại, không phải phương án khác.
ECHO = 0.72

_NEGATIVE_CUES = (
    ' not ', ' never ', 'except', 'ngoại trừ', 'không phải', 'không được',
    'không nằm', 'không thuộc', 'không đúng',
)


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFKC', (text or '').lower())
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', text)).strip()


def _cosine(a: str, b: str) -> float:
    """Độ giống nhau của hai đoạn chữ, tính trên n-gram ký tự và từ."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return 0.0
    try:
        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
        m = vec.fit_transform([a, b])
    except ValueError:
        return 0.0
    return float((m[0] @ m[1].T).toarray()[0][0])


def support(claim: str, excerpt: str) -> float:
    """0..1 — đoạn nguồn khẳng định mệnh đề này tới mức nào.

    Lấy câu trong đoạn nguồn giống mệnh đề nhất, rồi cộng thêm phần trăm từ
    của mệnh đề có mặt trong đoạn: một câu diễn đạt lại vẫn được điểm cao,
    còn một mệnh đề bịa thì không.
    """
    claim_n = _norm(claim)
    if not claim_n:
        return 0.0
    excerpt_n = _norm(excerpt)
    # Trích nguyên văn thì khỏi phải ước lượng: tài liệu nói đúng câu đó.
    if len(claim_n) > 3 and claim_n in excerpt_n:
        return 1.0
    sentences = _sentences(excerpt)
    best_sentence = max((_cosine(claim, s) for s in sentences), default=0.0)
    words = [w for w in claim_n.split() if len(w) > 2]
    covered = sum(1 for w in words if w in excerpt_n) / len(words) if words else 0.0
    # Phần từ có mặt là bằng chứng chắc hơn, nên nó nặng hơn.
    return round(min(1.0, 0.4 * best_sentence + 0.6 * covered), 3)


def _sentences(excerpt: str) -> list[str]:
    return [s for s in re.split(r'(?<=[.!?])\s+|\n+', excerpt or '') if s.strip()]


def answer_window(answer: str, excerpt: str) -> str:
    """Câu trong đoạn nguồn khẳng định đáp án — chỗ để soi các phương án nhiễu.

    Một nhiễu lấy từ chỗ khác của tài liệu là nhiễu *tốt*: nó nghe quen tai mà
    vẫn sai. Chỉ nhiễu đúng ngay tại chỗ tài liệu khẳng định đáp án mới là lỗi.
    """
    sentences = _sentences(excerpt)
    if not sentences:
        return excerpt or ''
    answer_n = _norm(answer)
    verbatim = [s for s in sentences if answer_n and answer_n in _norm(s)]
    if verbatim:
        return ' '.join(verbatim)
    return max(sentences, key=lambda s: _cosine(answer, s))


def is_negative_question(question: str) -> bool:
    """Câu hỏi dạng "điều nào KHÔNG..." — phép kiểm đáp án phải lật ngược."""
    raw = f' {(question or "")} '
    if re.search(r'\bNOT\b|\bEXCEPT\b|\bKHÔNG\b|\bNGOẠI TRỪ\b', raw):
        return True
    low = _norm(raw)
    return any(cue.strip() in low for cue in _NEGATIVE_CUES)


@dataclass
class QuestionReport:
    question: str
    answer_support: float
    distractor_support: dict[str, float]
    rivals: list[str] = field(default_factory=list)
    echoes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.flags


def score_question(item: dict, excerpt: str) -> QuestionReport:
    """Chấm một câu. `item` là dict như model sinh ra."""
    question = item.get('question_text') or item.get('question') or ''
    answer = item.get('correct_answer') or item.get('answer') or ''
    distractors = [d for d in (item.get('distractors') or []) if str(d).strip()]

    answer_support = support(answer, excerpt)
    d_support = {d: support(d, excerpt) for d in distractors}
    negative = is_negative_question(question)

    flags: list[str] = []
    rivals: list[str] = []
    echoes = [d for d in distractors if _cosine(d, answer) >= ECHO]

    if negative:
        # Đáp án đúng là thứ KHÔNG được nêu; nhiễu thì phải được nêu.
        if answer_support >= SUPPORTED:
            flags.append('negative_answer_supported')
        weak = [d for d, s in d_support.items() if s < RIVAL]
        if len(weak) == len(distractors) and distractors:
            flags.append('negative_distractors_unsupported')
    else:
        if answer_support < SUPPORTED:
            flags.append('answer_unsupported')
        # Nhiễu chỉ là lỗi khi tài liệu khẳng định nó ngay tại chỗ khẳng định
        # đáp án; khẳng định ở đoạn khác thì nó vẫn sai với câu hỏi này.
        window = answer_window(answer, excerpt)
        rivals = [d for d in distractors
                  if d not in echoes and support(d, window) >= RIVAL]
        if rivals:
            flags.append('rival_distractor')

    if echoes:
        flags.append('distractor_echoes_answer')
    if len(distractors) < 2:
        flags.append('too_few_distractors')
    if len(_norm(question).split()) < 4:
        flags.append('question_too_short')

    return QuestionReport(
        question=question,
        answer_support=answer_support,
        distractor_support=d_support,
        rivals=rivals,
        echoes=echoes,
        flags=flags,
    )


def score_set(items: list[dict], excerpt: str, duplicate_at: float = 0.85) -> dict:
    """Bảng điểm cho cả một bộ câu hỏi sinh cùng lúc, kèm số câu trùng nhau."""
    reports: list[QuestionReport] = []
    seen: list[str] = []
    duplicates = 0
    for item in items:
        question = item.get('question_text') or item.get('question') or ''
        if any(_cosine(question, s) >= duplicate_at for s in seen):
            duplicates += 1
            continue
        seen.append(question)
        reports.append(score_question(item, excerpt))

    flag_counts: dict[str, int] = {}
    for report in reports:
        for flag in report.flags:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1

    passed = sum(1 for r in reports if r.ok)
    total = len(items)
    return {
        'total': total,
        'scored': len(reports),
        'duplicates': duplicates,
        'passed': passed,
        # Câu trùng tính là trượt: bộ đề có hai câu giống nhau là bộ đề kém.
        'pass_rate': round(passed / total, 3) if total else 0.0,
        'flag_counts': flag_counts,
        'reports': reports,
    }
