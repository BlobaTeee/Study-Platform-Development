"""Quiz descriptions carried a "[source:1,3]" suffix; the relation (0005) has
it now, so the description goes back to being a description."""
import re

from django.db import migrations

_SUFFIX = re.compile(r'\s*\[source:[\d,]+\]')


def strip_suffix(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.filter(description__contains='[source:'):
        quiz.description = _SUFFIX.sub('', quiz.description or '').strip()
        quiz.save(update_fields=['description'])


def restore_suffix(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.prefetch_related('sources'):
        ids = sorted(s.id for s in quiz.sources.all())
        if not ids:
            continue
        tag = f"[source:{','.join(map(str, ids))}]"
        if tag not in (quiz.description or ''):
            quiz.description = f"{quiz.description or ''} {tag}".strip()
            quiz.save(update_fields=['description'])


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0005_quiz_sources')]

    operations = [migrations.RunPython(strip_suffix, restore_suffix)]
