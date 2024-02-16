# pylint: disable=too-many-locals
# pylint: disable=duplicate-code
"""Signal handlers for nautobot_ssot_vsphere."""

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.integrations.vsphere.constant import TAG_COLOR


def register_signals(sender):
    """Register signals for vSphere integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


# def create_custom_field(field_name: str, label: str, models: List, apps, cf_type: Optional[str] = "type_date"):
#     """Create custom field on a given model instance type.

#     Args:
#         field_name (str): Field Name
#         label (str): Label description
#         models (List): List of Django Models
#         apps: Django Apps
#         cf_type: (str, optional): Type of Field. Supports 'type_text' or 'type_date'. Defaults to 'type_date'.
#     """
#     ContentType = apps.get_model("contenttypes", "ContentType")  # pylint:disable=invalid-name
#     CustomField = apps.get_model("extras", "CustomField")  # pylint:disable=invalid-name
#     if cf_type == "type_date":
#         custom_field, _ = CustomField.objects.get_or_create(
#             type=CustomFieldTypeChoices.TYPE_DATE,
#             name=field_name,
#             defaults={
#                 "label": label,
#             },
#         )
#     else:
#         custom_field, _ = CustomField.objects.get_or_create(
#             type=CustomFieldTypeChoices.TYPE_TEXT,
#             name=field_name,
#             defaults={
#                 "label": label,
#             },
#         )
#     for model in models:
#         custom_field.content_types.add(ContentType.objects.get_for_model(model))
#     custom_field.save()


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create Tag and CustomField to note System of Record for SSoT."""
    # pylint: disable=invalid-name
    # Device = apps.get_model("dcim", "Device")
    # DeviceType = apps.get_model("dcim", "DeviceType")
    # DeviceRole = apps.get_model("dcim", "DeviceRole")
    # Interface = apps.get_model("dcim", "Interface")
    # IPAddress = apps.get_model("ipam", "IPAddress")
    # Site = apps.get_model("dcim", "Site")
    # VLAN = apps.get_model("ipam", "VLAN")
    Tag = apps.get_model("extras", "Tag")
    Cluster = apps.get_model("virtualization", "Cluster")
    ClusterGroup = apps.get_model("virtualization", "ClusterGroup")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    ClusterType = apps.get_model("virtualization", "ClusterType")
    VMInterface = apps.get_model("virtualization", "VMInterface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Status = apps.get_model("extras", "Status")
    CustomField = apps.get_model("extras", "CustomField")  # pylint:disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")  # pylint:disable=invalid-name

    status, _ = Status.objects.get_or_create(name="Suspended", description="Machine is in a suspended state")
    status.content_types.add(ContentType.objects.get_for_model(VirtualMachine))
    status.save()

    tag_sync_from_vsphere, _ = Tag.objects.get_or_create(
        name="SSoT Synced from vSphere",
        defaults={
            "name": "SSoT Synced from vSphere",
            "description": "Object synced at some point from VMWare vSphere to Nautobot",
            "color": TAG_COLOR,
        },
    )
    for model in [VirtualMachine, IPAddress]:
        tag_sync_from_vsphere.content_types.add(ContentType.objects.get_for_model(model))

    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        key="last_synced_from_vsphere_on",
        defaults={
            "label": "Last synced from vSphere on",
        },
    )

    synced_from_models = [
        # Device,
        # Interface,
        # Site,
        # VLAN,
        # DeviceRole,
        IPAddress,
        Cluster,
        ClusterGroup,
        ClusterType,
        VirtualMachine,
        VMInterface,
    ]
    for model in synced_from_models:
        custom_field.content_types.add(ContentType.objects.get_for_model(model))
    custom_field.save()
