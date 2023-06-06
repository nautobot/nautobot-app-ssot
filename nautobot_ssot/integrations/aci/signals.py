"""Post Migrate Welcome Wizard Script."""
import logging
import random
from django.utils.text import slugify
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot_ssot_aci.constant import PLUGIN_CFG

logger = logging.getLogger("rq.worker")


def aci_create_tag(apps, **kwargs):
    """Add a tag."""
    tag = apps.get_model("extras", "Tag")
    logger.info("Creating tags for ACI, interface status and Sites")

    tag.objects.update_or_create(
        name=PLUGIN_CFG.get("tag"),
        slug=slugify(PLUGIN_CFG.get("tag")),
        color=PLUGIN_CFG.get("tag_color"),
    )
    tag.objects.update_or_create(
        name=PLUGIN_CFG.get("tag_up"),
        slug=slugify(PLUGIN_CFG.get("tag_up")),
        color=PLUGIN_CFG.get("tag_up_color"),
    )
    tag.objects.update_or_create(
        name=PLUGIN_CFG.get("tag_down"),
        slug=slugify(PLUGIN_CFG.get("tag_down")),
        color=PLUGIN_CFG.get("tag_down_color"),
    )
    apics = PLUGIN_CFG.get("apics")
    for key in apics:
        if ("SITE" in key or "STAGE" in key) and not tag.objects.filter(name=apics[key]).exists():
            tag.objects.update_or_create(
                name=apics[key],
                slug=slugify(apics[key]),
                color="".join([random.choice("ABCDEF0123456789") for i in range(6)]),  # nosec
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
    site = apps.get_model("dcim", "Site")
    apics = PLUGIN_CFG.get("apics")
    for key in apics:
        if "SITE" in key:
            logger.info(f"Creating Site: {apics[key]}")
            site.objects.update_or_create(name=apics[key])


def device_custom_fields(apps, **kwargs):
    """Creating custom fields for interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Device = apps.get_model("dcim", "Device")
    CustomField = apps.get_model("extras", "CustomField")
    logger.info("Creating Device extra fields for PodID and NodeID")

    for device_cf_dict in [
        {
            "name": "aci_pod_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Cisco ACI Pod ID",
            "filter_logic": "loose",
            "description": "PodID added by SSoT plugin",
        },
        {
            "name": "aci_node_id",
            "type": CustomFieldTypeChoices.TYPE_INTEGER,
            "label": "Cisco ACI Node ID",
            "filter_logic": "loose",
            "description": "NodeID added by SSoT plugin",
        },
    ]:
        field, _ = CustomField.objects.get_or_create(name=device_cf_dict["name"], defaults=device_cf_dict)
        field.content_types.set([ContentType.objects.get_for_model(Device)])


def interface_custom_fields(apps, **kwargs):
    """Creating custom fields for interfaces."""
    ContentType = apps.get_model("contenttypes", "ContentType")
    Interface = apps.get_model("dcim", "Interface")
    CustomField = apps.get_model("extras", "CustomField")
    logger.info("Creating Interface extra fields for Optics")

    for interface_cf_dict in [
        {
            "name": "gbic_vendor",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Vendor",
            "filter_logic": "loose",
            "description": "Optic vendor added by SSoT plugin",
        },
        {
            "name": "gbic_type",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Type",
            "filter_logic": "loose",
            "description": "Optic type added by SSoT plugin",
        },
        {
            "name": "gbic_sn",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic S/N",
            "filter_logic": "loose",
            "description": "Optic S/N added by SSoT plugin",
        },
        {
            "name": "gbic_model",
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "label": "Optic Model",
            "filter_logic": "loose",
            "description": "Optic Model added by SSoT plugin",
        },
    ]:
        field, _ = CustomField.objects.get_or_create(name=interface_cf_dict["name"], defaults=interface_cf_dict)
        field.content_types.set([ContentType.objects.get_for_model(Interface)])
