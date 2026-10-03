from django.db.models import Avg
from django.utils import timezone
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import Answer, MockTest, Question, Quiz, QuizAttempt
from study_sessions import daily, scheduling
from study_sessions.models import CardReview
from users.timezones import zone_for
from . import insights


def _review_tallies(user):
    """Per-card correct/incorrect counts from the user's own review record.

    Flashcard.correct_count and .incorrect_count look like the obvious source
    but nothing writes to them; CardReview rows are what self-grading produces.
    """
    return insights.tally_reviews(
        list(CardReview.objects.filter(user=user).values('flashcard_id', 'result'))
    )


def _sources_by_flashcard(user):
    """Flashcard id -> ids of the sources it was generated from.

    One query over the through table for the whole collection, instead of a
    prefetch per card; the analytics page reads every card the user has.
    """
    by_card: dict[int, list[int]] = {}
    for card_id, source_id in (Flashcard.sources.through.objects
                               .filter(flashcard__user=user)
                               .values_list('flashcard_id', 'source_id')):
        by_card.setdefault(card_id, []).append(source_id)
    return by_card


def _questions_with_sources(user):
    """Every question the user owns as {'id', 'source_ids'}, one query.

    `values('id', 'quiz__sources')` yields one row per (question, source) and
    a row with `None` for a quiz with no sources, so rows are folded here.
    """
    by_question: dict[int, list[int]] = {}
    for row in Question.objects.filter(quiz__user=user).values('id', 'quiz__sources'):
        ids = by_question.setdefault(row['id'], [])
        if row['quiz__sources'] is not None:
            ids.append(row['quiz__sources'])
    return [{'id': qid, 'source_ids': ids} for qid, ids in by_question.items()]


class AnalyticsViewSet(viewsets.ViewSet):
    """Read-only study insights computed from the user's own activity.

    Everything here derives from what the user actually did: their cards, their
    review history, their documents. The previous taxonomy-backed recommender
    and learning path were removed — they could only suggest topics from a fixed
    5-subject STEM list, which does not match real uploaded documents.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        user = request.user
        completed = QuizAttempt.objects.filter(user=user, is_completed=True)
        avg_quiz_score = completed.aggregate(avg=Avg('score'))['avg']

        # Archived originals are replaced 1-for-1 by regeneration, not a net
        # addition, so counting them would inflate the lifetime total by one
        # per regeneration and disagree with the flashcards list page.
        flashcards = Flashcard.objects.filter(user=user, archived=False)
        reviews_qs = CardReview.objects.filter(user=user)
        correct = reviews_qs.filter(result__in=insights.CORRECT_RESULTS).count()
        incorrect = reviews_qs.filter(result__in=insights.INCORRECT_RESULTS).count()
        reviews = correct + incorrect

        return Response({
            'notebooks_count': Notebook.objects.filter(user=user).count(),
            'sources_count': Source.objects.filter(notebook__user=user).count(),
            'flashcards_count': flashcards.count(),
            'quizzes_count': Quiz.objects.filter(user=user).count(),
            'quiz_attempts_completed': completed.count(),
            'average_quiz_score': round(avg_quiz_score, 1) if avg_quiz_score is not None else None,
            'flashcard_reviews': reviews,
            'flashcard_correct': correct,
            'flashcard_incorrect': incorrect,
            'flashcard_accuracy': round(correct / reviews * 100, 1) if reviews else None,
        })

    @action(detail=False, methods=['get'])
    def recommendations(self, request):
        """How much study is owed now, and which documents you're weakest on.

        Question text is never fetched here, let alone returned: this endpoint
        reports on the schedule, and the study page is the only place a prompt
        should be seen.
        """
        user = request.user

        by_card = _sources_by_flashcard(user)
        cards = insights.attach_review_counts(
            # Archived originals keep their old next_review_date forever, so an
            # unfiltered count here would drift from due_today's own filtered
            # queryset and never come back into agreement.
            [{'id': c['id'], 'source_ids': by_card.get(c['id'], [])}
             for c in Flashcard.objects.filter(user=user, archived=False).values('id')],
            _review_tallies(user),
        )
        # Mastery is reported per notebook: a source's id is what the study
        # items are tagged with, so the lookup goes source -> notebook here.
        source_to_notebook = dict(
            Source.objects.filter(notebook__user=user).values_list('id', 'notebook_id')
        )
        notebook_titles = dict(
            Notebook.objects.filter(user=user).values_list('id', 'title')
        )

        # How much is owed comes from the SM-2 schedule the reviews built, so
        # this page and the study page cannot disagree about what is due. Counts
        # only: naming the cards here would show their questions minutes before
        # they are graded, inflating the grade and skewing the schedule.
        schedule = scheduling.latest_schedule(
            list(CardReview.objects.filter(user=user).latest_per_card()
                 .values('flashcard_id', 'next_review_date', 'review_date'))
        )
        today = timezone.localdate()
        due = scheduling.due_counts(cards, schedule, today)
        # The share for today next to the full counts: the dashboard leads with
        # the first, so two weeks away reads "40 today" and not "312 owed".
        due = {**due, **scheduling.todays_share(
            due, daily.budget_for(user, due['due'], today))}
        # An empty queue means the schedule is working. Without a return date it
        # reads exactly like a broken one, so the date travels with the counts.
        next_date, next_count = scheduling.next_due_batch(schedule, today)
        due = {**due, 'next_date': next_date, 'next_count': next_count}

        # Per-notebook mastery draws on every mode that grades an item against a
        # source. Flashcards alone would ignore the quiz answers on record, which
        # are the firmer evidence of the two — they are marked, not self-reported.
        events = insights.flashcard_events(cards) + insights.quiz_events(
            _questions_with_sources(user),
            list(Answer.objects.filter(quiz_attempt__user=user)
                 .values('question_id', 'is_correct')),
        )

        return Response({
            'due': due,
            'weak_notebooks': insights.per_notebook_mastery(
                events, source_to_notebook, notebook_titles),
        })

    ACTIVITY_DAYS = 14

    @action(detail=False, methods=['get'])
    def activity(self, request):
        """The last fourteen days of study, one entry per day.

        Days are the student's, not the server's: a review at 00:30 their time
        belongs to the night they sat up for, and the reminder email already
        speaks in their zone, so this must too.
        """
        user = request.user
        zone = zone_for(user)
        today = timezone.now().astimezone(zone).date()

        reviews = [
            {'date': when.astimezone(zone).date(), 'result': result}
            for when, result in CardReview.objects.grades().filter(user=user)
            .values_list('review_date', 'result')
        ]
        mock_tests = [
            {'date': when.astimezone(zone).date(), 'score': score}
            for when, score in MockTest.objects.filter(user=user, completed_at__isnull=False)
            .values_list('completed_at', 'score')
        ]
        data = insights.daily_activity(reviews, mock_tests, today=today,
                                       days=self.ACTIVITY_DAYS)
        for day in data['days']:
            day['date'] = day['date'].isoformat()
        return Response(data)
