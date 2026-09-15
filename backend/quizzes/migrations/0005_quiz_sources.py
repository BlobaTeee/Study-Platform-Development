"""Copy the "[source:1,3]" suffix quizzes carried in `description` into a real
relation. The suffix itself is stripped in 0006, once nothing reads it."""
import re

from django.db import migrations, models

_TAG = re.compile(r'source:([\d,]+)')


def _ids(text):
    match = _TAG.search(text or '')
    return [int(p) for p in match.group(1).split(',') if p] if match else []


def copy_description_tags_to_sources(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    Source = apps.get_model('notebooks', 'Source')
    Through = Quiz.sources.through
    existing = set(Source.objects.values_list('id', flat=True))
    rows = [
        Through(quiz_id=quiz_id, source_id=sid)
        for quiz_id, description in Quiz.objects.values_list('id', 'description')
        for sid in _ids(description) if sid in existing
    ]
    Through.objects.bulk_create(rows, ignore_conflicts=True)


def restore_description_tags(apps, schema_editor):
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
    dependencies = [
        ('quizzes', '0004_mock_test_review_freeze_and_reminder_skip'),
        ('notebooks', '0002_source_file_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='quiz',
            name='sources',
            field=models.ManyToManyField(
                blank=True, help_text='The documents this quiz was generated from.',
                related_name='quizzes', to='notebooks.source'),
        ),
        migrations.RunPython(copy_description_tags_to_sources, restore_description_tags),
    ]
