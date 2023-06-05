"""Signal handlers for nautobot_ssot_infoblox."""

from nautobot.extras.choices import CustomFieldTypeChoices, RelationshipTypeChoices
from nautobot_ssot_infoblox.constant import TAG_COLOR


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create Tag and CustomField to note System of Record for SSoT.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Prefix = apps.get_model("ipam", "Prefix")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Aggregate = apps.get_model("ipam", "Aggregate")
    Tag = apps.get_model("extras", "Tag")
    Relationship = apps.get_model("extras", "Relationship")
    VLAN = apps.get_model("ipam", "VLAN")

    Tag.objects.get_or_create(
        slug="ssot-synced-from-infoblox",
        defaults={
            "name": "SSoT Synced from Infoblox",
            "description": "Object synced at some point from Infoblox",
            "color": TAG_COLOR,
        },
    )
    Tag.objects.get_or_create(
        slug="ssot-synced-to-infoblox",
        defaults={
            "name": "SSoT Synced to Infoblox",
            "description": "Object synced at some point to Infoblox",
            "color": TAG_COLOR,
        },
    )
    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        name="ssot-synced-to-infoblox",
        defaults={
            "label": "Last synced to Infoblox on",
        },
    )
    for content_type in [
        ContentType.objects.get_for_model(Prefix),
        ContentType.objects.get_for_model(IPAddress),
        ContentType.objects.get_for_model(Aggregate),
    ]:
        custom_field.content_types.add(content_type)

    # add Prefix -> VLAN Relationship
    relationship_dict = {
        "name": "Prefix -> VLAN",
        "slug": "prefix_to_vlan",
        "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
        "source_type": ContentType.objects.get_for_model(Prefix),
        "source_label": "Prefix",
        "destination_type": ContentType.objects.get_for_model(VLAN),
        "destination_label": "VLAN",
    }
    Relationship.objects.get_or_create(name=relationship_dict["name"], defaults=relationship_dict)
