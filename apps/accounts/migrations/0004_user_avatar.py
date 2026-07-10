from django.db import migrations, models

import apps.accounts.models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_alter_user_actor_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='avatar',
            field=models.FileField(blank=True, upload_to=apps.accounts.models.user_avatar_upload_to),
        ),
    ]
