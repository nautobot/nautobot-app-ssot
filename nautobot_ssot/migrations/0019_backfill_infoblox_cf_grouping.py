from django.db import migrations

INFOBLOX_CF_METADATA = {
    "ssot_synced_to_infoblox": "Date the object was last synchronized to Infoblox. Managed by the Infoblox SSoT integration.",
    "dhcp_ranges": "DHCP ranges associated with a network. Managed by the Infoblox SSoT integration.",
    "mac_address": "MAC address used to create an Infoblox Fixed Address of type MAC. Managed by the Infoblox SSoT integration.",
    "fixed_address_comment": "Comment for the corresponding Infoblox Fixed Address record. Managed by the Infoblox SSoT integration.",
    "dns_a_record_comment": "Comment for the corresponding Infoblox DNS A record. Managed by the Infoblox SSoT integration.",
    "dns_host_record_comment": "Comment for the corresponding Infoblox DNS Host record. Managed by the Infoblox SSoT integration.",
    "dns_ptr_record_comment": "Comment for the corresponding Infoblox DNS PTR record. Managed by the Infoblox SSoT integration.",
}

INFOBLOX_GROUPING = "Infoblox"

# Per-Extensibility-Attribute CustomFields use dynamic slugified keys with no stable marker, so
# pre-existing ones can't be reliably identified and are intentionally not backfilled here.


def backfill_infoblox_cf_grouping(apps, schema_editor):
    """Backfill grouping/description on Infoblox-managed CustomFields created before they were added."""
    CustomField = apps.get_model("extras", "customfield")

    for key, description in INFOBLOX_CF_METADATA.items():
        for custom_field in CustomField.objects.filter(key=key):
            print(f'   Backfilling grouping/description on CustomField "{key}".')
            custom_field.grouping = INFOBLOX_GROUPING
            custom_field.description = description
            custom_field.save()


class Migration(migrations.Migration):
    dependencies = [
        ("nautobot_ssot", "0018_ssotinfobloxconfig_infoblox_location_ext_attr"),
    ]

    operations = [
        migrations.RunPython(
            code=backfill_infoblox_cf_grouping,
            reverse_code=migrations.operations.special.RunPython.noop,
        )
    ]
