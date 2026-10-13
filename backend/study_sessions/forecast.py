"""Dự báo trí nhớ: how many studied cards will still be remembered on test day.

For each card the student has graded, its memory state is rebuilt from the
reviews with FSRS-6 (ml_pipeline.fsrs_model; published parameters fitted
on Anki flashcard logs), which gives the chance it is recalled now and on
the day of the notebook's next planned test, or a week ahead when none is
planned. Notebook 08 shows why FSRS rather than the half-life regression
fitted there on Duolingo's word drills. Summed over a notebook,
those chances are the expected number of cards remembered.

It also says which cards to review first: those whose review today raises
their test-day chance the most. A review is not assumed to go well: its
gain is weighed by the chance of recalling the card when it is reviewed,
since a review that fails adds a wrong answer instead of a right one.
"""
from django.utils import timezone

from ml_pipeline.fsrs_model import AGAIN, GOOD, RATING, replay, retrievability, review

from .models import CardReview

DEFAULT_DAYS_AHEAD = 7
MAX_SUGGESTED = 20
#: Below this gain in test-day chance a review is not worth suggesting.
MIN_GAIN = 0.05


def forecast(user, cards) -> list[dict]:
    """[{notebook_id, title, has_exam, days_ahead, studied, unseen, now,
    at_exam, suggestion: {card_ids, at_exam}}], notebooks with something
    studied, most at risk first. Counts are expected numbers of cards."""
    from notebooks.models import Notebook
    from quizzes.models import PlannedTest

    now = timezone.now()
    card_notebook = dict(cards.values_list('id', 'notebook_id'))
    reviews: dict[int, list] = {}
    for card_id, result, when in (CardReview.objects.grades()
                                  .filter(user=user, flashcard_id__in=card_notebook)
                                  .values_list('flashcard_id', 'result', 'review_date')):
        if result in RATING:
            reviews.setdefault(card_id, []).append((when, RATING[result]))
    history = {card_id: replay(r) for card_id, r in reviews.items()}

    exams = {}
    for nb_id, when in (PlannedTest.objects.filter(user=user, sat_at__isnull=True, scheduled_for__gte=now)
                        .order_by('scheduled_for').values_list('notebook_id', 'scheduled_for')):
        exams.setdefault(nb_id, when)

    per_notebook: dict[int, dict] = {}
    for card_id, nb_id in card_notebook.items():
        entry = per_notebook.setdefault(nb_id, {'cards': [], 'unseen': 0})
        if card_id in history:
            entry['cards'].append(card_id)
        else:
            entry['unseen'] += 1

    titles = dict(Notebook.objects.filter(id__in=list(per_notebook)).values_list('id', 'title'))
    out = []
    for nb_id, entry in per_notebook.items():
        if not entry['cards']:
            continue
        exam = exams.get(nb_id)
        days_ahead = max(1, round((exam - now).total_seconds() / 86400)) if exam else DEFAULT_DAYS_AHEAD
        p_now, p_exam, gains = {}, {}, {}
        for card_id in entry['cards']:
            state = history[card_id]
            since = (now - state.last_review).total_seconds() / 86400
            p_now[card_id] = retrievability(since, state.stability)
            p_exam[card_id] = retrievability(since + days_ahead, state.stability)
            if_right = retrievability(days_ahead, review(state, GOOD, now).stability)
            if_wrong = retrievability(days_ahead, review(state, AGAIN, now).stability)
            reviewed = p_now[card_id] * if_right + (1 - p_now[card_id]) * if_wrong
            gains[card_id] = reviewed - p_exam[card_id]
        picked = sorted((c for c in gains if gains[c] >= MIN_GAIN), key=lambda c: -gains[c])[:MAX_SUGGESTED]
        at_exam = sum(p_exam.values())
        out.append({
            'notebook_id': nb_id,
            'title': titles.get(nb_id, ''),
            'has_exam': exam is not None,
            'days_ahead': days_ahead,
            'studied': len(entry['cards']),
            'unseen': entry['unseen'],
            'now': round(sum(p_now.values()), 1),
            'at_exam': round(at_exam, 1),
            'suggestion': {'card_ids': picked, 'at_exam': round(at_exam + sum(gains[c] for c in picked), 1)},
        })
    return sorted(out, key=lambda nb: nb['at_exam'] / nb['studied'])
