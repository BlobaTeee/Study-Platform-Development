from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('notebooks', '0003_normalise_extracted_text')]

    operations = [
        migrations.AlterField(
            model_name='source', name='file',
            field=models.FileField(blank=True, upload_to='notebook_sources/%Y/%m/'),
        ),
        migrations.AlterField(
            model_name='source', name='file_type',
            field=models.CharField(choices=[('pdf', 'PDF'), ('docx', 'Word'), ('pptx', 'PowerPoint'),
                                            ('text', 'Pasted text'), ('url', 'Web page')],
                                   default='pdf', max_length=10),
        ),
    ]
