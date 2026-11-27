"""The days a student studied on, counted the way the Progress calendar
counts them (analytics `activity`): a card graded, a quiz or mock test
finished, a practice problem worked on, an explanation written, or a live
question answered. The home page's streak is built from these, so the two
never disagree about whether a day counted."""


def study_days(user, zone) -> set:
    from exercises.models import ExerciseAttempt
    from live.models import LiveAnswer
    from quizzes.models import MockTest, QuizAttempt
    from .models import CardReview, FeynmanAttempt

    moments = [
        CardReview.objects.grades().filter(user=user).values_list('review_date', flat=True),
        MockTest.objects.filter(user=user, completed_at__isnull=False).values_list('completed_at', flat=True),
        QuizAttempt.objects.filter(user=user, is_completed=True, completed_at__isnull=False)
        .values_list('completed_at', flat=True),
        ExerciseAttempt.objects.filter(exercise__user=user).values_list('created_at', flat=True),
        FeynmanAttempt.objects.filter(user=user).values_list('created_at', flat=True),
        LiveAnswer.objects.filter(user=user).values_list('answered_at', flat=True),
    ]
    return {when.astimezone(zone).date() for rows in moments for when in rows if when}
