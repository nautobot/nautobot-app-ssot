# pylint: disable=duplicate-code
"""Nautobot Utils."""

import datetime
from typing import Any

from django.contrib.contenttypes.models import ContentType
from nautobot.core.choices import ColorChoices
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Tag
from nautobot.virtualization.models import (
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualMachine,
    VMInterface,
)

TODAY = datetime.date.today().isoformat()


def create_ssot_tag():
    """Create vSphere SSoT Tag."""
    ssot_tag, _ = Tag.objects.get_or_create(
        name="SSoT Synced from vSphere",
        defaults={
            "description": "Object synced at some point from VMWare vSphere to Nautobot",
            "color": ColorChoices.COLOR_LIGHT_GREEN,
        },
    )
    return ssot_tag


def tag_object(
    nautobot_object: Any,
    custom_field: str = "ssot-synced-from-vsphere",
    tag_name: str = "SSoT Synced from vSphere",
):
    """Apply the given tag and custom field to the identified object.

    Args:
        nautobot_object (Any): Nautobot ORM Object
        custom_field (str): Name of custom field to update
        tag_name (Optional[str], optional): Tag name. Defaults to "SSoT Synced From vsphere".
    """
    if tag_name == "SSoT Synced from vSphere":
        tag = create_ssot_tag()
    else:
        tag, _ = Tag.objects.get_or_create(name=tag_name)

    def _tag_object(nautobot_object):
        """Apply custom field and tag to object, if applicable."""
        if hasattr(nautobot_object, "tags"):
            nautobot_object.tags.add(tag)
        if hasattr(nautobot_object, "cf"):
            # Ensure that the "ssot-synced-from-vsphere" custom field is present
            if not any(
                cfield for cfield in CustomField.objects.all() if cfield.natural_slug == "ssot_synced_from_vsphere"
            ):
                custom_field_obj, _ = CustomField.objects.get_or_create(
                    type=CustomFieldTypeChoices.TYPE_DATE,
                    key="ssot_synced_from_vsphere",
                    defaults={
                        "label": "Last synced from vSphere on",
                    },
                )
                synced_from_models = [
                    Cluster,
                    ClusterType,
                    ClusterGroup,
                    VirtualMachine,
                    VMInterface,
                ]
                for model in synced_from_models:
                    custom_field_obj.content_types.add(ContentType.objects.get_for_model(model))
                custom_field_obj.validated_save()

            # Update custom field date stamp
            nautobot_object.cf[custom_field] = TODAY
        nautobot_object.validated_save()

    _tag_object(nautobot_object)
    # Ensure proper save
