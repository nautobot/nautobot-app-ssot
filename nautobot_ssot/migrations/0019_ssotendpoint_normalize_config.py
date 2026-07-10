"""Add normalize_config to SSOTEndpoint for canonical field staging."""

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0018_generic_ssot"),
    ]

    operations = [
        migrations.AddField(
            model_name="ssotendpoint",
            name="normalize_config",
            field=models.JSONField(
                blank=True,
                default=list,
                encoder=django.core.serializers.json.DjangoJSONEncoder,
                help_text=(
                    "Ordered list of canonical field definitions used to normalize raw API "
                    'records before mapping. Each entry: {"name": str, "source": JMESPath, '
                    '"fallback": JMESPath, "transforms": [{"type": str, "config": {...}}, ...]}.'
                ),
            ),
        ),
    ]
