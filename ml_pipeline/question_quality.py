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

# Từ đơn phải khớp nguyên từ — "footnote" không phải là "not". Cụm nhiều từ
# thì khớp chuỗi con là an toàn.
_NEGATIVE_WORDS = r'\b(?:not|never|except|cannot|excluding)\b'
_NEGATIVE_PHRASES = (
    'ngoại trừ', 'không phải', 'không được', 'không nằm', 'không thuộc',
    'không đúng', 'không hề', 'least likely',
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


def _numbers(text: str) -> list[str]:
    return re.findall(r'\d[\d.,]*', text or '')


def echoes_answer(distractor: str, answer: str) -> bool:
    """Nhiễu chỉ là bản nhại đáp án khi nó không khác đáp án ở con số.

    "At least 4 billion" so với "At least 8 billion" giống nhau gần hết về chữ,
    nhưng đó là một bộ nhiễu bằng số hoàn toàn hợp lệ.
    """
    if _numbers(distractor) != _numbers(answer):
        return False
    return _cosine(distractor, answer) >= ECHO


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
    score = min(1.0, 0.4 * best_sentence + 0.6 * covered)

    # "At least 4 billion" dùng gần hết chữ của "at least 8 billion" nhưng tài
    # liệu không nói vậy. Chỉ xét khi tài liệu viết số bằng chữ số, để một đoạn
    # viết "tám tỷ" không làm đáp án "8 tỷ" bị coi là bịa.
    claim_numbers, excerpt_numbers = _numbers(claim), _numbers(excerpt)
    if claim_numbers and excerpt_numbers and not set(claim_numbers) <= set(excerpt_numbers):
        score *= 0.4
    return round(score, 3)


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


def _word_forms(text: str) -> set[str]:
    """Whole words, with a trailing plural "s" folded so "lifelines" meets "lifeline"."""
    return {w[:-1] if len(w) > 4 and w.endswith('s') else w for w in _norm(text).split()}


def distinctive_support(distractor: str, answer: str, passage: str) -> float:
    """0..1 — how much of what sets this distractor apart the passage states.

    Words the distractor shares with the answer ("the ... principle") say
    nothing about whether it is true; only its own words can. "The accuracy
    principle" next to the answer "The integrity and confidentiality
    principle" is judged on "accuracy" alone. Whole words, so "act" never
    matches inside "actually". A distractor with no words of its own (a
    different number, say) scores 0 — that case is the number rule's.
    """
    answer_words = _word_forms(answer)
    own = [w for w in _word_forms(distractor) if len(w) > 2 and w not in answer_words]
    if not own:
        return 0.0
    present = _word_forms(passage)
    return sum(1 for w in own if w in present) / len(own)


def is_negative_question(question: str) -> bool:
    """Câu hỏi dạng "điều nào KHÔNG..." — phép kiểm đáp án phải lật ngược."""
    raw = question or ''
    if re.search(r'\bNOT\b|\bEXCEPT\b|\bKHÔNG\b|\bNGOẠI TRỪ\b', raw):
        return True
    low = _norm(raw)
    if re.search(_NEGATIVE_WORDS, low):
        return True
    return any(phrase in low for phrase in _NEGATIVE_PHRASES)


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
    echoes = [d for d in distractors if echoes_answer(d, answer)]

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
                  if d not in echoes and distinctive_support(d, answer, window) >= RIVAL]
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


def rank_by_quality(items: list[dict], excerpt_key: str = '_excerpt') -> list[dict]:
    """Questions ordered best first: no flags, then fewer flags, else as given.

    Nothing is dropped. Generation asks for a few more questions than it
    needs and takes from the top, so a flawed question is only used when
    there are not enough sound ones — a short quiz would be worse than one
    question with a weak distractor. Each item is scored against the passage
    it was generated from, stored under `excerpt_key`.
    """
    # A fill-in-the-blank question has no distractors to judge.
    scored = [(0 if item.get('kind') == 'fill_blank' else len(score_question(item, item.get(excerpt_key) or '').flags),
               i, item) for i, item in enumerate(items)]
    return [item for _, _, item in sorted(scored, key=lambda t: (t[0], t[1]))]
