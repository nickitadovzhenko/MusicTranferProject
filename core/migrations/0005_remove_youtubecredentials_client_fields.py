from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_alter_spotify_token_access_token_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='youtubecredentials',
            name='client_id',
        ),
        migrations.RemoveField(
            model_name='youtubecredentials',
            name='client_secret',
        ),
    ]
