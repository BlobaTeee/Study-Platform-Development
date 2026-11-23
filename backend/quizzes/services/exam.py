"""Mock tests in the shape of a real exam: parts of different answer kinds,
each marked by the exam's own rules (docs/specs/2026-11-23-exam-format-mock-tests.md).

The arithmetic (templates, true/false scoring, which questions suit typing)
has no Django imports so it is testable on its own; writing true/false items
asks the model and is kept at the bottom.
"""
from __future__ import annotations

import json
import random

#: Each template totals 10 points. (kind, how many, points each)
TEMPLATES: dict[str, dict] = {
    'thpt': {'duration': 90, 'parts': [('choice', 12, 0.25), ('true_false', 4, 1.0), ('short', 6, 0.5)]},
    'test45': {'duration': 45, 'parts': [('choice', 12, 0.25), ('true_false', 2, 1.0), ('written', 1, 5.0)]},
}

#: Share of a true/false question's points for 0..4 statements right, as the
#: THPT exam marks it (0.1, 0.25, 0.5, 1 of one point).
TF_SHARE = {0: 0.0, 1: 0.1, 2: 0.25, 3: 0.5, 4: 1.0}
TF_STATEMENTS = 4

#: A Part III question is typed, so its answer must be short enough to type.
SHORT_ANSWER_MAX_WORDS = 6


#: Minutes a question of each kind is given, to time a mixed paper by its
#: length (a written problem: per point it is worth).
MINUTES_PER = {'choice': 2, 'true_false': 5, 'short': 4, 'written': 6}


def mixed_parts(rng=random) -> dict:
    """A paper whose parts are drawn at random each time, so no two sittings
    have the same shape, always worth 10 points with each kind marked as the
    exam marks it: 8 or 12 multiple choice (0.25 each), 2 to 4 true/false (1
    each), and the rest split between short answers (0.5 each, at most six)
    and, when they do not fill it, one written problem worth what is left."""
    choice = rng.choice((8, 12))
    tf = rng.choice((2, 3, 4))
    rest = 10 - choice * 0.25 - tf                      # 3 to 6 points
    short = rng.choice([n for n in (2, 4, 6) if n * 0.5 <= rest])
    written = rest - short * 0.5
    parts = [('choice', choice, 0.25), ('true_false', tf, 1.0), ('short', short, 0.5)]
    if written > 0:
        parts.append(('written', 1, float(written)))
    minutes = sum(MINUTES_PER[k] * (pts if k == 'written' else n) for k, n, pts in parts)
    return {'duration': int(min(120, max(20, 5 * -(-minutes // 5)))), 'parts': parts}


def template(name: str) -> dict | None:
    """A paper's shape: a fixed one by name, or a fresh random one for "mixed"."""
    if name == 'mixed':
        return mixed_parts()
    return TEMPLATES.get(name)


def tf_earned(marks: dict, statements: list[dict], points: float) -> tuple[float, int]:
    """Points earned on a true/false question and how many statements were right."""
    right = sum(1 for st in statements if marks.get(st['label']) is st['answer'])
    share = TF_SHARE.get(right, 0.0) if len(statements) == TF_STATEMENTS else right / max(1, len(statements))
    return round(points * share, 2), right


def written_earned(grade: dict, checkpoint_count: int, points: float) -> float:
    """A written answer earns its points in proportion to the checkpoints met;
    a pass earns them all."""
    if grade.get('verdict') == 'passed':
        return points
    met = len(grade.get('met') or [])
    return round(points * met / checkpoint_count, 2) if checkpoint_count else 0.0


def suits_typing(correct_answer: str) -> bool:
    """Whether a multiple-choice answer is short enough to ask without options."""
    words = str(correct_answer or '').split()
    return 0 < len(words) <= SHORT_ANSWER_MAX_WORDS


def parse_marks(raw: str) -> dict:
    """A true/false answer as stored: JSON {label: bool}; anything else is no marks."""
    try:
        data = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, bool)} if isinstance(data, dict) else {}


# ---- writing true/false items ------------------------------------------------------------

TF_PER_REQUEST = 6
MAX_MATERIAL_CHARS = 12000


def write_true_false(notebook, count: int) -> list:
    """Ask the model for true/false items from the notebook's key points and
    keep the ones whose every statement quotes its passage. Returns the
    saved TrueFalseItem rows (possibly fewer than asked, or none)."""
    from ml_pipeline.language import language_name
    from notebooks.services.key_points import _find, _searchable
    from notebooks.services.writing_style import WRITING_STYLE, tidy_prose
    from exercises.services.common import PracticeUnavailable, ask, items_of, language_of
    from quizzes.models import TrueFalseItem

    sources = [s for s in notebook.sources.all() if (s.extracted_text or '').strip()]
    if not sources:
        return []
    material, texts = [], {}
    for src in sources:
        texts[src.id] = src.extracted_text
        points = src.key_points or []
        body = '\n'.join(f'- {p.get("point", "")}\n  "{(p.get("passage") or "")[:500]}"' for p in points) \
            if points else src.extracted_text[:3000]
        material.append(f'[Document {src.id}: {src.title}]\n{body}')
    material_text = '\n\n'.join(material)[:MAX_MATERIAL_CHARS]
    lang = language_of(material_text[:3000])
    prompt = f"""Write {min(count, TF_PER_REQUEST)} true/false exam questions from this study material, in
{language_name(lang)}, in the format of the Vietnamese national exam: each question has a short
stem setting a context, then exactly {TF_STATEMENTS} statements a), b), c), d) about it, and the
student marks each statement true or false.

- Mix true and false statements; never all true or all false. A false statement changes one
  thing the material says (a value, a cause, a direction), so it reads as plausible.
- Order the statements from easier to harder.
- Each statement has a "basis": an exact quote from the material (one phrase or sentence, at
  least five words) that settles it, copied character for character, and the "document" id
  it comes from.
- Write any mathematics in LaTeX between $...$.

Material:
{material_text}

{WRITING_STYLE}

Return ONLY valid JSON:
{{"questions": [{{"document": 1, "stem": "...", "statements": [{{"label": "a", "text": "...",
"answer": true, "basis": "exact quote"}}]}}]}}"""
    try:
        reply = ask(prompt)
    except PracticeUnavailable:
        return []
    flats = {sid: _searchable(t)[0] for sid, t in texts.items()}
    saved = []
    for item in items_of(reply, 'questions'):
        if not isinstance(item, dict):
            continue
        src_id = item.get('document') if item.get('document') in texts else None
        stem = tidy_prose(str(item.get('stem') or ''))
        raw = item.get('statements') if isinstance(item.get('statements'), list) else []
        statements = []
        for label, st in zip('abcd', raw):
            if not isinstance(st, dict) or not isinstance(st.get('answer'), bool):
                break
            text = tidy_prose(str(st.get('text') or ''))
            basis = str(st.get('basis') or '').strip()
            haystacks = [flats[src_id]] if src_id else list(flats.values())
            if not text or not basis or not any(_find(basis, flat) is not None for flat in haystacks):
                break                      # rests on nothing the student was given
            statements.append({'label': label, 'text': text[:400], 'answer': st['answer'], 'basis': basis[:300]})
        answers = {st['answer'] for st in statements}
        if len(stem) < 5 or len(statements) != TF_STATEMENTS or len(answers) < 2:
            continue
        saved.append(TrueFalseItem.objects.create(notebook=notebook, source_id=src_id, stem=stem[:1500],
                                                  statements=statements))
    return saved
