# Generated by Django 3.2.16 on 2023-06-14 18:09

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0005_sync_compressed_diff"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sync",
            name="diff",
        ),
        migrations.RenameField(
            model_name="sync",
            old_name="compressed_diff",
            new_name="diff",
        ),
    ]
