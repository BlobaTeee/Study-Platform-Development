from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0006_strip_source_tags_from_descriptions')]

    operations = [
        migrations.AddField(model_name='answer', name='mode',
                            field=models.CharField(choices=[('choice', 'Multiple choice'), ('typed', 'Typed')],
                                                   default='choice', max_length=10)),
        migrations.AddField(model_name='answer', name='verdict',
                            field=models.CharField(blank=True, default='', max_length=10)),
        migrations.AddField(model_name='answer', name='graded_how',
                            field=models.CharField(blank=True, default='', max_length=10)),
        migrations.AddField(model_name='answer', name='overridden',
                            field=models.BooleanField(default=False)),
    ]
