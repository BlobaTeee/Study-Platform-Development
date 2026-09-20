"""Each question remembers the source and passage it was generated from,
and a sitting freezes both. Existing questions of a single-source quiz get
that source; their passage is unknown and stays blank."""
from django.db import migrations, models
import django.db.models.deletion


def backfill_single_source(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    Question = apps.get_model('quizzes', 'Question')
    for quiz in Quiz.objects.prefetch_related('sources'):
        ids = list(quiz.sources.values_list('id', flat=True))
        if len(ids) == 1:
            Question.objects.filter(quiz=quiz, source__isnull=True).update(source_id=ids[0])


class Migration(migrations.Migration):
    dependencies = [
        ('quizzes', '0008_retire_stacked_quizzes'),
        ('notebooks', '0004_source_text_and_url'),
    ]

    operations = [
        migrations.AddField(model_name='question', name='source',
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='questions', to='notebooks.source')),
        migrations.AddField(model_name='question', name='source_excerpt',
                            field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='mocktestquestion', name='source',
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                                    related_name='+', to='notebooks.source')),
        migrations.AddField(model_name='mocktestquestion', name='source_excerpt',
                            field=models.TextField(blank=True, default='')),
        migrations.RunPython(backfill_single_source, migrations.RunPython.noop),
    ]
