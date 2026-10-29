"""Give one account weeks of believable study history, for a live demo.

    python manage.py seed_demo --email demo@example.com [--reset] [--days 18]

The progress features (study calendar, forgotten cards, mix-ups, test-day
forecast) only have something to show after weeks of use. This builds that
for one account: three notebooks of two documents each, written from SciQ
(real science questions with their supporting passages, already in
datasets/processed), with cards, quizzes and a simulated student who
studies most evenings, keeps forgetting one topic, sits a few mock tests and
has a test coming up.

The account must exist already: sign up and sign in once, so the backend has
provisioned it. Nothing else is touched, no AI request is made, and an
account that already has notebooks is refused unless --reset is given, which
first deletes that account's study data.
"""
import random
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

#: (notebook, [(document title, keywords that pick its passages)]).
PLAN = [
    ('Biology', [('Cells and genetics', ('cell', 'dna', 'gene', 'protein', 'chromosome')),
                 ('Evolution and ecosystems', ('evolution', 'species', 'ecosystem', 'population', 'natural selection'))]),
    ('Chemistry', [('Atoms and bonding', ('atom', 'electron', 'proton', 'bond', 'ion')),
                   ('Chemical reactions', ('reaction', 'acid', 'base', 'catalyst', 'solution'))]),
    ('Physics', [('Forces and motion', ('force', 'motion', 'velocity', 'acceleration', 'gravity')),
                 ('Energy and waves', ('energy', 'wave', 'light', 'heat', 'frequency'))]),
]
#: The topic the simulated student keeps forgetting.
WEAK_DOCUMENT = 'Chemical reactions'
#: Two ideas the student keeps mixing up, per document: its quiz carries
#: SciQ questions whose answer is one and a distractor the other, and a wrong
#: answer there picks the other one. That is what "What you mix up" finds.
CONFUSIONS = {'Chemical reactions': ('acid', 'base'), 'Cells and genetics': ('mitosis', 'meiosis')}
CONFUSION_QUESTIONS = 5
PASSAGES_PER_DOCUMENT = 32
CARDS_PER_DOCUMENT = 12
QUESTIONS_PER_DOCUMENT = 10
NEW_CARDS_PER_DAY = 8
TEST_IN_DAYS = 9


class Command(BaseCommand):
    help = 'Fill one existing account with demo notebooks and weeks of study history (no AI requests).'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)
        parser.add_argument('--reset', action='store_true', help="Delete this account's study data first.")
        parser.add_argument('--days', type=int, default=18, help='How many days of history to simulate.')
        parser.add_argument('--seed', type=int, default=7)

    def handle(self, *args, email, reset=False, days=18, seed=7, **kwargs):
        from notebooks.models import Notebook
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f'No account with email {email}. Sign up and sign in once first.')
        if Notebook.objects.filter(user=user).exists() and not reset:
            raise CommandError(f'{email} already has notebooks. Pass --reset to replace its study data.')
        rng = random.Random(seed)
        rows = _sciq()
        with transaction.atomic():
            if reset:
                _clear(user)
            content = _build_content(user, rows, rng)
            _simulate(user, content, days, rng)
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {email}: {sum(len(d["cards"]) for d in content)} cards, '
            f'{sum(len(d["questions"]) for d in content)} questions, {days} days of history.'))


def _sciq():
    import pandas as pd
    path = Path(settings.BASE_DIR).parent / 'datasets' / 'processed' / 'sciq.parquet'
    if not path.exists():
        raise CommandError(f'{path} is missing; see datasets/README.md.')
    df = pd.read_parquet(path)
    df = df[df.support.str.len() > 80].drop_duplicates('question')
    return df.to_dict('records')


def _clear(user):
    from notebooks.models import Notebook
    from quizzes.models import MockTest, PlannedTest, Quiz
    from study_sessions.models import CardReview, FeynmanAttempt, StudyStreak
    CardReview.objects.filter(user=user).delete()
    MockTest.objects.filter(user=user).delete()
    PlannedTest.objects.filter(user=user).delete()
    FeynmanAttempt.objects.filter(user=user).delete()
    StudyStreak.objects.filter(user=user).delete()
    Quiz.objects.filter(user=user).delete()
    Notebook.objects.filter(user=user).delete()       # sources and cards go with them


def _build_content(user, rows, rng) -> list[dict]:
    from flashcards.models import Flashcard
    from flashcards.services.card_format import checked_cloze
    from notebooks.models import Notebook, Source
    from quizzes.models import Question, Quiz

    used = set()
    documents = []
    confusing = {}
    for doc_title, (a, b) in CONFUSIONS.items():
        confusing[doc_title] = [r for r in rows if _swaps(r, a, b)][:CONFUSION_QUESTIONS]
        used.update(r['question'] for r in confusing[doc_title])
    for nb_title, docs in PLAN:
        notebook = Notebook.objects.create(user=user, title=nb_title)
        for doc_title, words in docs:
            picked = [r for r in rows if r['question'] not in used
                      and any(re.search(rf'\b{w}', (r['question'] + ' ' + r['support']).lower()) for w in words)]
            picked = picked[:PASSAGES_PER_DOCUMENT]
            used.update(r['question'] for r in picked)
            mixed = confusing.get(doc_title, [])
            text = '\n\n'.join(r['support'].strip() for r in picked + mixed)
            source = Source.objects.create(
                notebook=notebook, title=doc_title, file_type='text', extracted_text=text, status='ready',
                gemini_summary=f'{doc_title}: ' + ' '.join(_sentences(picked[0]['support'])[:2]))

            cards = []
            for i, r in enumerate(picked[:CARDS_PER_DOCUMENT]):
                answer = r['correct_answer'].strip()
                question, kind = r['question'].strip(), 'basic'
                if i % 4 == 3:
                    # Every fourth card is fill-in-the-blank, from the passage itself.
                    sentence = next((s for s in _sentences(r['support']) if answer.lower() in s.lower()), '')
                    blanked = re.sub(re.escape(answer), '___', sentence, count=1, flags=re.I) if sentence else ''
                    if blanked and checked_cloze(blanked, answer):
                        question, kind = checked_cloze(blanked, answer), 'cloze'
                card = Flashcard.objects.create(
                    user=user, notebook=notebook, question=question, answer=answer[:1].upper() + answer[1:],
                    explanation=_explanation(r['support'], r['question'], answer), kind=kind, is_public=False)
                card.sources.set([source])
                cards.append(card)

            quiz = Quiz.objects.create(user=user, title=f'Quiz: {doc_title}', is_published=True,
                                       description=f'Generated from {doc_title}')
            quiz.sources.set([source])
            questions = []
            for order, r in enumerate(mixed + picked[CARDS_PER_DOCUMENT:CARDS_PER_DOCUMENT + QUESTIONS_PER_DOCUMENT]):
                options = [r['correct_answer'], r['distractor1'], r['distractor2'], r['distractor3']]
                rng.shuffle(options)
                questions.append(Question.objects.create(
                    quiz=quiz, question_text=r['question'], question_type='multiple_choice', options=options,
                    correct_answer=r['correct_answer'], explanation=_explanation(r['support'], r['question'], r['correct_answer']),
                    order=order, source=source, source_excerpt=r['support'][:2000]))
            documents.append({'notebook': notebook, 'title': doc_title, 'cards': cards, 'questions': questions,
                              'weak': doc_title == WEAK_DOCUMENT, 'confusion': CONFUSIONS.get(doc_title),
                              'confusing': {q.id for q in questions[:len(mixed)]}})
    return documents


def _swaps(row, a: str, b: str) -> bool:
    """The answer is about one idea and a distractor about the other."""
    distractors = [row['distractor1'], row['distractor2'], row['distractor3']]
    right = row['correct_answer'].lower()
    return any((a in right and b in d.lower()) or (b in right and a in d.lower()) for d in distractors)


def _opposite(question, confusion) -> str | None:
    """The option naming the other idea of the pair, if there is one."""
    if not confusion:
        return None
    a, b = confusion
    right = question.correct_answer.lower()
    other = b if a in right else a if b in right else None
    return next((o for o in question.options if o != question.correct_answer and other and other in o.lower()), None)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text or '') if len(s.strip()) > 20]


_STOPWORDS = {'what', 'which', 'when', 'where', 'does', 'that', 'this', 'with', 'from', 'into', 'than',
              'their', 'there', 'they', 'have', 'been', 'will', 'would', 'about', 'called', 'kind', 'type'}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 3 and w not in _STOPWORDS}


def _explanation(support: str, question: str, answer: str) -> str:
    """The passage's sentence that gives the answer, for a card or question.

    SciQ passages often open with something else ("The warm-air vent is placed
    near the floor..."), so the first sentence would explain nothing. Prefer a
    sentence that names the answer, then the one sharing most words with the
    question. A wrong explanation is worse than none, so with neither it is
    left blank.
    """
    asked = _words(question)
    pattern = re.compile(rf'\b{re.escape(answer.strip())}\b', re.I) if answer.strip() else None

    def score(sentence: str) -> tuple[int, int]:
        names_answer = bool(pattern and pattern.search(sentence))
        return int(names_answer), len(asked & _words(sentence))

    ranked = sorted(_sentences(support), key=score, reverse=True)
    if not ranked or score(ranked[0]) == (0, 0):
        return ''
    return ranked[0][:300]


def _simulate(user, documents, days, rng):
    """A student who studies most evenings: due cards plus a few new ones,
    recalled with the chance FSRS gives (much less for the weak topic), a
    mock test every few days, and a planned test ahead."""
    from ml_pipeline.fsrs_model import RATING, replay, retrievability
    from quizzes.models import MockTest, MockTestQuestion, PlannedTest
    from study_sessions.models import CardReview

    all_cards = [(c, d['weak']) for d in documents for c in d['cards']]
    history: dict[int, list] = {}
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    mock_days = [days // 3, (2 * days) // 3, days - 2]
    # Chemistry, Biology, Chemistry: the two notebooks with a mix-up, so it
    # shows in more than one sitting.
    mock_notebooks = [documents[2]['notebook'].id, documents[0]['notebook'].id, documents[2]['notebook'].id]

    for back in range(days, 0, -1):
        day = today - timedelta(days=back)
        evening = timezone.make_aware(datetime.combine(day, time(19, 0)), tz)
        if rng.random() < 0.22 and back not in (1, 2):
            continue                                   # a day off
        due = []
        for card, weak in all_cards:
            if card.id in history:
                latest = CardReview.objects.filter(flashcard=card).order_by('-review_date').first()
                if latest.next_review_date and latest.next_review_date <= day:
                    due.append((card, weak))
        fresh = [cw for cw in all_cards if cw[0].id not in history][:NEW_CARDS_PER_DAY]
        for minute, (card, weak) in enumerate(due + fresh):
            when = evening + timedelta(minutes=minute)
            past = history.get(card.id, [])
            if past:
                state = replay(past)
                chance = retrievability((when - state.last_review).total_seconds() / 86400, state.stability)
            else:
                chance = 0.8
            chance *= 0.3 if weak else 1.0
            grade = ('easy' if rng.random() < 0.25 else 'good') if rng.random() < chance else 'hard'
            with mock.patch('django.utils.timezone.now', return_value=when):
                CardReview.record(user, card, grade)
            history.setdefault(card.id, []).append((when, RATING[grade]))

        if (days - back) in mock_days:
            nb_id = mock_notebooks[mock_days.index(days - back)]
            _sit_mock_test(user, documents, nb_id, evening + timedelta(hours=1), rng, MockTest, MockTestQuestion)

    biology = documents[0]['notebook']
    PlannedTest.objects.create(
        user=user, notebook=biology, question_count=20, duration_minutes=30,
        scheduled_for=timezone.make_aware(datetime.combine(today + timedelta(days=TEST_IN_DAYS), time(9, 0)), tz))


def _sit_mock_test(user, documents, nb_id, when, rng, MockTest, MockTestQuestion):
    """Ten questions from one notebook, every mix-up question among them. The
    weak topic goes worse, and a mix-up question is mostly answered with the
    other idea of the pair."""
    docs = [d for d in documents if d['notebook'].id == nb_id]
    mixups = [(q, d) for d in docs for q in d['questions'] if q.id in d['confusing']]
    rest = [(q, d) for d in docs for q in d['questions'] if q.id not in d['confusing']]
    paper = mixups + rng.sample(rest, max(0, min(10 - len(mixups), len(rest))))
    with mock.patch('django.utils.timezone.now', return_value=when):
        test = MockTest.objects.create(user=user, notebook_id=nb_id, question_count=len(paper), duration_minutes=20)
    right = 0
    for order, (q, d) in enumerate(paper):
        swapped = _opposite(q, d['confusion']) if q.id in d['confusing'] else None
        correct = rng.random() < (0.2 if swapped else 0.4 if d['weak'] else 0.75)
        wrong_choice = swapped or next(o for o in q.options if o != q.correct_answer)
        right += correct
        MockTestQuestion.objects.create(
            mock_test=test, question=q, order=order, question_text=q.question_text, options=q.options,
            correct_answer=q.correct_answer, explanation=q.explanation, source=q.source,
            source_excerpt=q.source_excerpt, user_answer=q.correct_answer if correct else wrong_choice,
            is_correct=correct, answered_at=when + timedelta(minutes=order + 1))
    MockTest.objects.filter(id=test.id).update(completed_at=when + timedelta(minutes=15),
                                               score=round(100 * right / len(paper), 1))
