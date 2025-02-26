"""Signals for ACI integration."""

# pylint: disable=logging-fstring-interpolation, invalid-name
import logging
import random

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.aci.constant import PLUGIN_CFG

logger = logging.getLogger("nautobot.ssot.aci")


def register_signals(sender):
    """Registers signals."""
    nautobot_database_ready.connect(aci_create_tag, sender=sender)
    nautobot_database_ready.connect(aci_create_manufacturer, sender=sender)
    nautobot_database_ready.connect(aci_create_site, sender=sender)
    nautobot_database_ready.connect(device_custom_fields, sender=sender)
    nautobot_database_ready.connect(interface_custom_fields, sender=sender)


def _ensure_tag(apps, name, color):
    """Ensure tag exists and properly configured."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    tag = apps.get_model("extras", "Tag")
    _tag = tag.objects.get_or_create(name=name)[0]
    if _tag.color != color:
        _tag.color = color
        _tag.save()
    for content_type in ContentType.objects.all():
        if content_type not in _tag.content_types.all():
            _tag.content_types.add(content_type)


def aci_create_tag(apps, **kwargs):
    """Add a tag."""
    tag = apps.get_model("extras", "Tag")
    logger.info("Creating tags for ACI, interface status and Sites")
    _ensure_tag(apps=apps, name=PLUGIN_CFG.get("tag"), color=PLUGIN_CFG.get("tag_color"))
    _ensure_tag(apps=apps, name=PLUGIN_CFG.get("tag_up"), color=PLUGIN_CFG.get("tag_up_color"))
    _ensure_tag(apps=apps, name=PLUGIN_CFG.get("tag_down"), color=PLUGIN_CFG.get("tag_down_color"))
    _ensure_tag(apps=apps, name="ACI_MULTISITE", color="03a9f4")

    apics = PLUGIN_CFG.get("apics")
    if apics:
        for key in apics:
            if ("SITE" in key or "STAGE" in key) and not tag.objects.filter(name=apics[key]).exists():
                _ensure_tag(
                    apps=apps,
                    name=apics[key],
                    color="".join([random.choice("ABCDEF0123456789") for i in range(6)]),  # noqa: S311
                )


def aci_create_manufacturer(apps, **kwargs):
    """Add manufacturer."""
    manufacturer = apps.get_model("dcim", "Manufacturer")
    logger.info(f"Creating manufacturer: {PLUGIN_CFG.get('manufacturer_name')}")
    manufacturer.objects.update_or_create(
        name=PLUGIN_CFG.get("manufacturer_name"),
    )


def aci_create_site(apps, **kwargs):
    """Add site."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    Site = apps.get_model("dcim", "Location")
    Prefix = apps.get_model("ipam", "Prefix")
    Vlan = apps.get_model("ipam", "VLAN")
    location_type = apps.get_model("dcim", "LocationType")
    status = apps.get_model("extras", "Status")
    apics = PLUGIN_CFG.get("apics")
    loc_type = location_type.objects.update_or_create(name="Site")[0]
    loc_type.content_types.add(ContentType.objects.get_for_model(Device))
    loc_type.content_types.add(ContentType.objects.get_for_model(Prefix))
    loc_type.content_types.add(ContentType.objects.get_for_model(Vlan))
    active_status = status.objects.update_or_create(name="Active")[0]
    if apics:
        for key in apics:
            if "SITE" in key:
                logger.info(f"Creating Site: {apics[key]}")
                Site.objects.update_or_create(name=apics[key], location_type=loc_type, status=active_status)


def device_custom_fields(apps, **kwargs):
    """Creating custom fields for interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")
    logger.info("Creating Device extra fields for PodID and NodeID")

    for device_cf_dict in [
        {
            "key": "aci_pod_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Cisco ACI Pod ID",
            "filter_logic": "loose",
            "description": "PodID added by SSoT app",
        },
        {
            "key": "aci_node_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Cisco ACI Node ID",
            "filter_logic": "loose",
            "description": "NodeID added by SSoT app",
        },
    ]:
        field, _ = CustomField.objects.get_or_create(key=device_cf_dict["key"], defaults=device_cf_dict)
        field.content_types.set([ContentType.objects.get_for_model(Device)])


def interface_custom_fields(apps, **kwargs):
    """Creating custom fields for interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Interface = apps.get_model("dcim", "Interface")
    CustomField = apps.get_model("extras", "CustomField")
    logger.info("Creating Interface extra fields for Optics")

    for interface_cf_dict in [
        {
            "key": "gbic_vendor",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Vendor",
            "filter_logic": "loose",
            "description": "Optic vendor added by SSoT app",
        },
        {
            "key": "gbic_type",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Type",
            "filter_logic": "loose",
            "description": "Optic type added by SSoT app",
        },
        {
            "key": "gbic_sn",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic S/N",
            "filter_logic": "loose",
            "description": "Optic S/N added by SSoT app",
        },
        {
            "key": "gbic_model",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Model",
            "filter_logic": "loose",
            "description": "Optic Model added by SSoT app",
        },
    ]:
        field, _ = CustomField.objects.get_or_create(key=interface_cf_dict["key"], defaults=interface_cf_dict)
        field.content_types.set([ContentType.objects.get_for_model(Interface)])
