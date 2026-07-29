from django.db import migrations

SOURCE_TAG_PREFIX = 'source:'


def _source_ids(tag):
    """The source ids in a `source:1,2` tag, or an empty list."""
    if not tag or not tag.startswith(SOURCE_TAG_PREFIX):
        return []
    return [part for part in tag[len(SOURCE_TAG_PREFIX):].split(',') if part.strip().isdigit()]


def link_cards_to_notebooks(apps, schema_editor):
    """Fill in the notebook every existing card was generated from.

    Cards predate the foreign key, so their only link to a notebook is the
    `source:1,2` string in `tags`. Resolved through the sources that still
    exist; a card whose sources are all gone stays null rather than being
    deleted, because a migration is the wrong place to throw away a learner's
    review history.
    """
    Flashcard = apps.get_model('flashcards', 'Flashcard')
    Source = apps.get_model('notebooks', 'Source')

    notebook_of = dict(Source.objects.values_list('id', 'notebook_id'))
    if not notebook_of:
        return

    # One UPDATE per distinct tag rather than per card: a tag names exactly one
    # notebook, and a learner has far fewer source selections than cards.
    tags = (Flashcard.objects.filter(tags__startswith=SOURCE_TAG_PREFIX, notebook__isnull=True)
            .values_list('tags', flat=True).distinct())
    for tag in list(tags):
        for raw_id in _source_ids(tag):
            notebook_id = notebook_of.get(int(raw_id))
            if notebook_id is not None:
                Flashcard.objects.filter(tags=tag).update(notebook_id=notebook_id)
                break


def unlink_cards(apps, schema_editor):
    """Reversible, but deliberately does nothing.

    Clearing the column would also wipe the links that generation has written
    since — and rolling back past here drops the column outright in 0004
    anyway, so there is nothing this could usefully undo.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('flashcards', '0004_flashcard_notebook'),
    ]

    operations = [
        migrations.RunPython(link_cards_to_notebooks, unlink_cards),
    ]
