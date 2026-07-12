from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notebooks', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='source',
            name='file_type',
            field=models.CharField(
                choices=[('pdf', 'PDF'), ('docx', 'Word'), ('pptx', 'PowerPoint')],
                default='pdf',
                max_length=10,
            ),
        ),
    ]
