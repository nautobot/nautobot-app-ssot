# Migration to update CustomFields that are Solarwinds to SolarWinds.
from django.db import migrations


def update_solarwinds_customfields(apps, schema_editor):
    """Update CustomFields that are Solarwinds to SolarWinds."""
    for app, model in [
        ("dcim", "Device"),
        ("dcim", "Interface"),
        ("ipam", "Prefix"),
        ("ipam", "IPAddress"),
    ]:
        model = apps.get_model(app, model)
        cf_list = []
        for instance in model.objects.filter(_custom_field_data__system_of_record="Solarwinds").iterator():
            print(f"System of Record CustomField on {instance} is being updated from Solarwinds to SolarWinds.")
            instance._custom_field_data["system_of_record"] = "SolarWinds"
            cf_list.append(instance)
        model.objects.bulk_update(cf_list, ["_custom_field_data"], 1000)


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0012_ssotinfobloxconfig_infoblox_network_view_to_namespace_map"),
    ]

    operations = [
        migrations.RunPython(
            code=update_solarwinds_customfields,
            reverse_code=migrations.operations.special.RunPython.noop,
        )
    ]
