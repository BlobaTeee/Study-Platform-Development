import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add the notebook column. The backfill is 0005.

    Non-atomic on purpose: adding a foreign key to a table that already has
    rows queues the constraint's validation triggers, and Postgres then
    refuses to build the column's index inside the same transaction
    ("cannot CREATE INDEX ... because it has pending trigger events").
    Running the statements outside one transaction lets each commit in turn.
    The operation is a single nullable AddField, so there is no half-applied
    state worth guarding against; the backfill that does have one is kept in
    its own atomic migration.
    """

    atomic = False

    dependencies = [
        ('flashcards', '0003_flashcard_regeneration_attempts'),
        ('notebooks', '0002_source_file_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='flashcard',
            name='notebook',
            field=models.ForeignKey(blank=True, help_text='Deleted along with its notebook.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='flashcards', to='notebooks.notebook'),
        ),
    ]
