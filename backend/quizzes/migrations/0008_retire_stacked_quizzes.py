"""Before regeneration replaced quizzes, every press stacked another quiz on
the same sources. Keep the newest published quiz per (user, exact source
set); unpublish the rest. Nothing is deleted — attempts on retired quizzes
still count toward mastery."""
from django.db import migrations


def retire_stacked(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    Through = Quiz.sources.through
    by_quiz = {}
    for quiz_id, source_id in Through.objects.values_list('quiz_id', 'source_id'):
        by_quiz.setdefault(quiz_id, set()).add(source_id)
    newest_per_set = {}
    for quiz in Quiz.objects.filter(is_published=True).order_by('-created_at'):
        sources = frozenset(by_quiz.get(quiz.id, ()))
        if not sources:
            continue
        key = (quiz.user_id, sources)
        if key in newest_per_set:
            quiz.is_published = False
            quiz.save(update_fields=['is_published'])
        else:
            newest_per_set[key] = quiz.id


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0007_answer_typed_grading')]

    operations = [migrations.RunPython(retire_stacked, migrations.RunPython.noop)]
