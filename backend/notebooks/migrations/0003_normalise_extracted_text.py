"""Fold ligatures and full-width forms in text extracted before ingest
normalised it (see notebooks/services/textnorm.py)."""
import unicodedata

from django.db import migrations


def normalise_existing(apps, schema_editor):
    Source = apps.get_model('notebooks', 'Source')
    for source in Source.objects.exclude(extracted_text=''):
        fixed = unicodedata.normalize('NFKC', source.extracted_text)
        if fixed != source.extracted_text:
            source.extracted_text = fixed
            source.save(update_fields=['extracted_text'])


class Migration(migrations.Migration):
    dependencies = [('notebooks', '0002_source_file_type')]

    operations = [migrations.RunPython(normalise_existing, migrations.RunPython.noop)]
