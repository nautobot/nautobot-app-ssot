from django.db import migrations
from nautobot.extras.utils import FeatureQuery

CF_KEY_CHANGE_MAP = {
    "servicenow_last_synchronized": "ssot-synced-to-servicenow",
    "ssot_last_synchronized": "ssot-synced-from-ipfabric",
    "ipfabric_site_id": "ipfabric-site-id",
}


def migrate_dashed_custom_fields_to_underscored(apps, schema_editor):
    CustomField = apps.get_model("extras", "customfield")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for key in CF_KEY_CHANGE_MAP.values():
        for custom_field in CustomField.objects.filter(key=key):
            original_key = custom_field.key
            updated_key = CF_KEY_CHANGE_MAP[key]
            print(
                f'CustomField instance "{custom_field.label}" key attribute "{original_key}" is being changed to "{updated_key}".'
            )
            custom_field.key = updated_key
            custom_field.save()

    for ct in ContentType.objects.filter(FeatureQuery("custom_fields").get_query()):
        relevant_custom_fields = CustomField.objects.filter(content_types=ct)
        if not relevant_custom_fields.exists():
            continue
        model = apps.get_model(ct.app_label, ct.model)
        cf_list = []
        for instance in model.objects.all():
            new_custom_field_data = {}
            for cf in relevant_custom_fields:
                new_custom_field_data[cf.key] = instance._custom_field_data.pop(CF_KEY_CHANGE_MAP.get(cf.key), None)
            instance._custom_field_data = new_custom_field_data
            cf_list.append(instance)
        model.objects.bulk_update(cf_list, ["_custom_field_data"], 1000)


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "0006_ssotservicenowconfig"),
    ]

    operations = [
        migrations.RunPython(
            code=migrate_dashed_custom_fields_to_underscored,
            reverse_code=migrations.operations.special.RunPython.noop,
        )
    ]
