# pylint: disable=invalid-name
"""Nautobot signal handler functions for aristavc_sync."""

from django.apps import apps as global_apps
from django.db.models.signals import post_migrate
from nautobot.extras.choices import CustomFieldTypeChoices, RelationshipTypeChoices

from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config


# pylint: disable-next=unused-argument
def register_signals(sender):
    """Register signals for Arista CloudVision integration."""
    post_migrate.connect(post_migrate_create_custom_fields)
    post_migrate.connect(post_migrate_create_manufacturer)
    post_migrate.connect(post_migrate_create_platform)

    if get_config().create_controller:
        post_migrate.connect(post_migrate_create_controller_relationship)


def post_migrate_create_custom_fields(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create CustomField records."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")

    for device_cf_dict in [
        {
            "key": "arista_eostrain",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "EOS Train",
        },
        {
            "key": "arista_eos",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "EOS Version",
        },
        {
            "key": "arista_ztp",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "label": "ztp",
        },
        {
            "key": "arista_pimbidir",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "pimbidir",
        },
        {
            "key": "arista_pim",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "pim",
        },
        {
            "key": "arista_bgp",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "bgp",
        },
        {
            "key": "arista_mpls",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "label": "mpls",
        },
        {
            "key": "arista_systype",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "systype",
        },
        {
            "key": "arista_mlag",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "mlag",
        },
        {
            "key": "arista_tapagg",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "TAP Aggregation",
        },
        {
            "key": "arista_sflow",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "sFlow",
        },
        {
            "key": "arista_terminattr",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "TerminAttr Version",
        },
        {
            "key": "arista_topology_network_type",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Network Type",
        },
        {"key": "arista_topology_type", "type": CustomFieldTypeChoices.TYPE_TEXT, "label": "Topology Type"},
        {
            "key": "arista_topology_rack",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Rack",
        },
        {
            "key": "arista_topology_pod",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Topology Pod",
        },
        {
            "key": "arista_vxlanConfigured",
            "type": CustomFieldTypeChoices.TYPE_BOOLEAN,
            "label": "VXLAN Configured",
        },
    ]:
        field, _ = CustomField.objects.update_or_create(
            key=device_cf_dict["key"],
            defaults=device_cf_dict,
        )
        field.content_types.set([ContentType.objects.get_for_model(Device)])


def post_migrate_create_manufacturer(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Arista Manufacturer."""
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Manufacturer.objects.update_or_create(name="Arista")


def post_migrate_create_platform(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Arista Platform."""
    Platform = apps.get_model("dcim", "Platform")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform.objects.update_or_create(
        name="arista.eos.eos",
        defaults={
            "napalm_driver": "eos",
            "network_driver": "arista_eos",
            "manufacturer": Manufacturer.objects.get(name="Arista"),
        },
    )

    if get_config().create_controller:
        Platform.objects.get_or_create(
            name="Arista EOS-CloudVision",
            manufacturer=Manufacturer.objects.get(name="Arista"),
        )


def post_migrate_create_controller_relationship(apps=global_apps, **kwargs):
    """Callback function for post_migrate() -- create Relationship for Controller -> Device."""
    Device = apps.get_model("dcim", "Device")
    Relationship = apps.get_model("extras", "Relationship")
    ContentType = apps.get_model("contenttypes", "ContentType")
    relationship_dict = {
        "label": "Controller -> Device",
        "key": "controller_to_device",
        "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        "source_type": ContentType.objects.get_for_model(Device),
        "source_label": "Controller",
        "destination_type": ContentType.objects.get_for_model(Device),
        "destination_label": "Device",
    }
    Relationship.objects.update_or_create(label=relationship_dict["label"], defaults=relationship_dict)
