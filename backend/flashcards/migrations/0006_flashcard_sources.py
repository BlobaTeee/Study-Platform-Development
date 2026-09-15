"""Copy the `source:1,3` tag into a real relation. `tags` itself is removed
in 0007, once nothing reads it any more."""
import re

from django.db import migrations, models

_TAG = re.compile(r'source:([\d,]+)')


def _ids(text):
    match = _TAG.search(text or '')
    return [int(p) for p in match.group(1).split(',') if p] if match else []


def copy_tags_to_sources(apps, schema_editor):
    Flashcard = apps.get_model('flashcards', 'Flashcard')
    Source = apps.get_model('notebooks', 'Source')
    Through = Flashcard.sources.through
    # Ids of sources that no longer exist are dropped: carrying them was the
    # orphan problem this relation replaces.
    existing = set(Source.objects.values_list('id', flat=True))
    rows = [
        Through(flashcard_id=card_id, source_id=sid)
        for card_id, tags in Flashcard.objects.values_list('id', 'tags')
        for sid in _ids(tags) if sid in existing
    ]
    Through.objects.bulk_create(rows, ignore_conflicts=True)


def rebuild_tags_from_sources(apps, schema_editor):
    Flashcard = apps.get_model('flashcards', 'Flashcard')
    for card in Flashcard.objects.prefetch_related('sources'):
        ids = sorted(s.id for s in card.sources.all())
        card.tags = f"source:{','.join(map(str, ids))}" if ids else None
        card.save(update_fields=['tags'])


class Migration(migrations.Migration):
    dependencies = [
        ('flashcards', '0005_link_flashcards_to_notebooks'),
        ('notebooks', '0002_source_file_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='flashcard',
            name='sources',
            field=models.ManyToManyField(
                blank=True, help_text='The documents this card was generated from.',
                related_name='flashcards', to='notebooks.source'),
        ),
        migrations.RunPython(copy_tags_to_sources, rebuild_tags_from_sources),
    ]
