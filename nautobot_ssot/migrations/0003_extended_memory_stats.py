# Generated by Django 3.1.13 on 2022-01-11 06:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nautobot_ssot", "0002_performance_metrics"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="sync",
            name="memory_peak",
        ),
        migrations.RemoveField(
            model_name="sync",
            name="memory_size",
        ),
        migrations.RemoveField(
            model_name="sync",
            name="memory_usage",
        ),
        migrations.AddField(
            model_name="sync",
            name="diff_memory_peak",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="diff_memory_size",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="load_source_memory_peak",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="load_source_memory_size",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="load_target_memory_peak",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="load_target_memory_size",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="sync_memory_peak",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sync",
            name="sync_memory_size",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
