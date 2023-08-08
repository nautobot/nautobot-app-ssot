# pylint: disable=invalid-name
"""Nautobot signal handler functions for aristavc_sync."""

from django.apps import apps as global_apps
from django.db.models.signals import post_migrate
from nautobot.extras.choices import CustomFieldTypeChoices, RelationshipTypeChoices

from nautobot_ssot.integrations.aristacv.constant import APP_SETTINGS


# pylint: disable-next=unused-argument
def register_signals(sender):
    """Register signals for Arista CloudVision integration."""
    post_migrate.connect(post_migrate_create_custom_fields)
    post_migrate.connect(post_migrate_create_manufacturer)
    post_migrate.connect(post_migrate_create_platform)

    if APP_SETTINGS.get("create_controller"):
        post_migrate.connect(post_migrate_create_controller_relationship)


def post_migrate_create_custom_fields(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create CustomField records."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")

    for device_cf_dict in [
        {
            "name": "arista_eostrain",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "EOS Train",
        },
        {
            "name": "arista_eos",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "EOS Version",
        },
        {
            "name": "arista_ztp",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "label": "ztp",
        },
        {
            "name": "arista_pimbidir",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "pimbidir",
        },
        {
            "name": "arista_pim",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "pim",
        },
        {
            "name": "arista_bgp",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "bgp",
        },
        {
            "name": "arista_mpls",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "label": "mpls",
        },
        {
            "name": "arista_systype",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "systype",
        },
        {
            "name": "arista_mlag",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "mlag",
        },
        {
            "name": "arista_tapagg",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "TAP Aggregation",
        },
        {
            "name": "arista_sflow",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "sFlow",
        },
        {
            "name": "arista_terminattr",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "TerminAttr Version",
        },
        {
            "name": "arista_topology_network_type",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Network Type",
        },
        {"name": "arista_topology_type", "type": CustomFieldTypeChoices.TYPE_TEXT, "label": "Topology Type"},
        {
            "name": "arista_topology_rack",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Rack",
        },
        {
            "name": "arista_topology_pod",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Pod",
        },
    ]:
        field, _ = CustomField.objects.update_or_create(
            name=device_cf_dict["name"], defaults=device_cf_dict, slug=device_cf_dict["name"]
        )
        field.content_types.set([ContentType.objects.get_for_model(Device)])


def post_migrate_create_manufacturer(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Arista Manufacturer."""
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Manufacturer.objects.update_or_create(name="Arista", slug="arista")


def post_migrate_create_platform(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Arista Platform."""
    Platform = apps.get_model("dcim", "Platform")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform.objects.get_or_create(
        name="arista.eos.eos",
        slug="arista_eos",
        napalm_driver="eos",
        manufacturer=Manufacturer.objects.get(slug="arista"),
    )

    if APP_SETTINGS.get("create_controller"):
        Platform.objects.get_or_create(
            name="Arista EOS-CloudVision",
            slug="arista_eos_cloudvision",
            manufacturer=Manufacturer.objects.get(slug="arista"),
        )


def post_migrate_create_controller_relationship(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Relationship for Controller -> Device."""
    Device = apps.get_model("dcim", "Device")
    Relationship = apps.get_model("extras", "Relationship")
    ContentType = apps.get_model("contenttypes", "ContentType")
    relationship_dict = {
        "name": "Controller -> Device",
        "slug": "controller_to_device",
        "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        "source_type": ContentType.objects.get_for_model(Device),
        "source_label": "Controller",
        "destination_type": ContentType.objects.get_for_model(Device),
        "destination_label": "Device",
    }
    Relationship.objects.update_or_create(name=relationship_dict["name"], defaults=relationship_dict)
