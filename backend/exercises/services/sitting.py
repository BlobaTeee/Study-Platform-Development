"""A set picked from a real paper, sat as that paper: timed, no hints, the
whole of it marked at the end, out of 10, part by part.

On 2026-11-25 the user found a real paper added to practice more like an
exam than the mock tests the app writes; practice only lacked the clock and
the mark. This turns the set's problems into the rows of an exam-shaped mock
test (quizzes.MockTest, template "paper"), so it is sat, marked and reviewed
there. Each row keeps the problem it came from (reference["exercise_id"]):
what is missed goes back to practice to be done again.
"""
import math

#: What each kind is worth before the paper is scaled to 10. As the THPT
#: paper weighs them: a Part I question 0.25, a Part II question (four
#: statements) 1, a Part III answer 0.25; a written problem 1.
BASE_POINTS = {'choice': 0.25, 'true_false': 1.0, 'short': 0.25, 'written': 1.0}
#: Minutes each kind is given, to time the paper by what it holds.
MINUTES = {'choice': 1.5, 'true_false': 4, 'short': 3, 'written': 10}
TOTAL = 10.0


def _row(exercise) -> dict:
    """One problem as a paper row's fields: its kind as the exam part it
    belongs to, what it is marked against, and its figures."""
    ref = dict(exercise.reference or {})
    kind = ref.get('kind') or 'written'
    keep = {'exercise_id': exercise.id, 'figures': list(exercise.figures or [])}
    row = {'question_text': exercise.prompt, 'source_id': exercise.source_id}

    if kind == 'choice' and ref.get('answer') and ref.get('options'):
        options = [f"{o.get('label')}. {o.get('text')}" for o in ref['options'] if isinstance(o, dict)]
        correct = next((text for o, text in zip(ref['options'], options)
                        if str(o.get('label')).upper() == str(ref['answer']).upper()), '')
        if correct:
            return {**row, 'section': 'choice', 'options': options, 'correct_answer': correct,
                    'reference': keep}
    if kind == 'true_false':
        statements = [{'label': st['label'], 'text': st['text'], 'answer': st['answer']}
                      for st in ref.get('statements') or []
                      if isinstance(st, dict) and isinstance(st.get('answer'), bool)]
        if statements:
            return {**row, 'section': 'true_false', 'statements': statements, 'reference': keep}
    if kind == 'short' and str(ref.get('answer') or '').strip():
        return {**row, 'section': 'short', 'correct_answer': str(ref['answer'])[:500],
                'reference': {**keep, 'answer': ref['answer'], 'accept': list(ref.get('accept') or [])}}
    # Written, or a keyed kind whose key did not come through: marked
    # against its rubric, as practice marks it.
    return {**row, 'section': 'written', 'reference': {**ref, **keep}}


def paper_from_set(exercises) -> tuple[list[dict], int]:
    """The rows of the paper, in the set's order, each with its points (the
    whole worth 10), and the minutes it is given."""
    rows = [_row(ex) for ex in exercises]
    base = sum(BASE_POINTS[r['section']] for r in rows) or 1.0
    for r in rows:
        r['points'] = round(BASE_POINTS[r['section']] * TOTAL / base, 3)
    minutes = sum(MINUTES[r['section']] for r in rows)
    return rows, int(min(180, max(10, 5 * math.ceil(minutes / 5))))
