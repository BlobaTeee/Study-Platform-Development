from django.db import migrations, models

import users.models


class Migration(migrations.Migration):
    dependencies = [('users', '0002_userprofile_supabase_uid')]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='timezone',
            field=models.CharField(default=users.models._default_timezone, max_length=64),
        ),
    ]
