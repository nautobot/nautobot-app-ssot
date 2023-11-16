from django.db import migrations
from nautobot.extras.utils import FeatureQuery

CF_KEY_CHANGE_MAP = {
    "servicenow_last_synchronized": "ssot-synced-to-servicenow",
    "last_synced_from_sor": "ssot-synced-from-ipfabric",
    "ipfabric_site_id": "ipfabric-site-id",
    "ssot_synced_to_infoblox": "ssot-synced-to-infoblox",
}


def replace_dashed_custom_fields(apps, schema_editor):
    CustomField = apps.get_model("extras", "customfield")
    ContentType = apps.get_model("contenttypes", "ContentType")

    for new_key, old_key in CF_KEY_CHANGE_MAP.items():
        for custom_field in CustomField.objects.filter(key=old_key):
            original_key = custom_field.key
            updated_key = CF_KEY_CHANGE_MAP[new_key]
            print(
                f'CustomField instance "{custom_field.label}" key attribute "{original_key}" is being changed to "{updated_key}".'
            )
            custom_field.key = updated_key
            custom_field.save()

    for ct in ContentType.objects.filter(FeatureQuery("custom_fields").get_query()):
        relevant_custom_fields = CustomField.objects.filter(content_types=ct, key__in=CF_KEY_CHANGE_MAP.values())
        if not relevant_custom_fields.exists():
            continue
        model = apps.get_model(ct.app_label, ct.model)
        cf_list = []
        for instance in model.objects.all():
            new_custom_field_data = instance._custom_field_data.copy()
            for cf in relevant_custom_fields:
                if cf.key not in new_custom_field_data:
                    new_custom_field_data[cf.key] = instance._custom_field_data.pop(CF_KEY_CHANGE_MAP.get(cf.key), None)
            instance._custom_field_data = new_custom_field_data
            cf_list.append(instance)
        model.objects.bulk_update(cf_list, ["_custom_field_data"], 1000)


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0006_ssotservicenowconfig"),
    ]

    operations = [
        migrations.RunPython(
            code=replace_dashed_custom_fields,
            reverse_code=migrations.operations.special.RunPython.noop,
        )
    ]
