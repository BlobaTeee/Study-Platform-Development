"""The source tag lives in Flashcard.sources since 0006; nothing reads `tags`."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('flashcards', '0006_flashcard_sources')]

    operations = [
        migrations.RemoveField(model_name='flashcard', name='tags'),
    ]
