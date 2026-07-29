from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the regeneration attempt counter.

    The AlterField on `id` that makemigrations bundles in is pre-existing
    DEFAULT_AUTO_FIELD drift, unrelated to this feature, so it is left out
    rather than smuggled into an unrelated migration.
    """

    dependencies = [
        ('flashcards', '0002_flashcard_variants'),
    ]

    operations = [
        migrations.AddField(
            model_name='flashcard',
            name='regeneration_attempts',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Failed regeneration attempts since this card was flagged.',
            ),
        ),
    ]
