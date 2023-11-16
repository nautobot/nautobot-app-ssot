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
        if not CustomField.objects.filter(key=new_key).exists():
            for custom_field in CustomField.objects.filter(key=old_key):
                original_key = custom_field.key
                print(
                    f'   CustomField instance "{custom_field.label}" key attribute "{original_key}" is being changed to "{new_key}".'
                )
                custom_field.key = new_key
                custom_field.save()

    for ct in ContentType.objects.filter(FeatureQuery("custom_fields").get_query()):
        model = apps.get_model(ct.app_label, ct.model)
        cf_list = []
        for instance in model.objects.all():
            for new_cf, old_cf in CF_KEY_CHANGE_MAP.items():
                if old_cf in instance._custom_field_data and new_cf in instance._custom_field_data:
                    print(f"CustomField {new_cf} on {instance} is being set to {instance._custom_field_data[old_cf]}.")
                    instance._custom_field_data[new_cf] = instance._custom_field_data.pop(old_cf)
            cf_list.append(instance)
        model.objects.bulk_update(cf_list, ["_custom_field_data"], 1000)

    for old_cf in CF_KEY_CHANGE_MAP.values():
        for custom_field in CustomField.objects.filter(key=old_cf):
            print(f"Deleting CustomField {custom_field.key}.")
            custom_field.delete()


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
