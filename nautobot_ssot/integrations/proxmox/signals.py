# pylint: disable=too-many-locals
# pylint: disable=duplicate-code
# pylint: disable=invalid-name

"""Signal handlers for the nautobot_ssot Proxmox VE integration."""

from django.conf import settings
from nautobot.core.choices import ColorChoices
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import (
    CustomFieldTypeChoices,
    RelationshipTypeChoices,
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)

from nautobot_ssot.integrations.proxmox.constants import (
    CLUSTER_TYPE_NAME,
    HOST_RELATIONSHIP_KEY,
    HOST_RELATIONSHIP_LABEL,
    NODE_CPU_COUNT_CF,
    NODE_DEVICE_ROLE_NAME,
    NODE_DEVICE_TYPE_NAME,
    NODE_LOCATION_NAME,
    NODE_MANUFACTURER_NAME,
    NODE_MEMORY_GB_CF,
    NODE_PVE_VERSION_CF,
    SSOT_CUSTOM_FIELD_KEY,
    SSOT_CUSTOM_FIELD_LABEL,
    SSOT_TAG_DESCRIPTION,
    SSOT_TAG_NAME,
)

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for the Proxmox VE integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)
    nautobot_database_ready.connect(create_default_proxmox_config, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create Tag, CustomField, ClusterType, Statuses, and node-Device prerequisites for SSoT."""
    Tag = apps.get_model("extras", "Tag")
    Role = apps.get_model("extras", "Role")
    Status = apps.get_model("extras", "Status")
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")
    ClusterType = apps.get_model("virtualization", "ClusterType")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    VMInterface = apps.get_model("virtualization", "VMInterface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Device = apps.get_model("dcim", "Device")
    Interface = apps.get_model("dcim", "Interface")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Location = apps.get_model("dcim", "Location")
    LocationType = apps.get_model("dcim", "LocationType")

    device_ct = ContentType.objects.get_for_model(Device)
    interface_ct = ContentType.objects.get_for_model(Interface)
    vm_ct = ContentType.objects.get_for_model(VirtualMachine)
    vminterface_ct = ContentType.objects.get_for_model(VMInterface)
    ipaddress_ct = ContentType.objects.get_for_model(IPAddress)

    # Statuses used by the default VM status map and node Devices.
    active_status, _ = Status.objects.get_or_create(name="Active")
    offline_status, _ = Status.objects.get_or_create(name="Offline")
    suspended_status, _ = Status.objects.get_or_create(
        name="Suspended", defaults={"description": "Machine is in a suspended/paused state"}
    )
    for status in (active_status, offline_status, suspended_status):
        for content_type in (vm_ct, vminterface_ct):
            status.content_types.add(content_type)
    # Node Devices and their DCIM Interfaces use the Active status.
    active_status.content_types.add(interface_ct)

    # SSoT tag applied to every synced object.
    tag_sync_from_proxmox, _ = Tag.objects.get_or_create(
        name=SSOT_TAG_NAME,
        defaults={
            "description": SSOT_TAG_DESCRIPTION,
            "color": ColorChoices.COLOR_GREEN,
        },
    )
    for content_type in (device_ct, vm_ct, vminterface_ct, ipaddress_ct):
        tag_sync_from_proxmox.content_types.add(content_type)

    custom_field, _ = CustomField.objects.get_or_create(
        key=SSOT_CUSTOM_FIELD_KEY,
        defaults={"type": CustomFieldTypeChoices.TYPE_DATETIME, "label": SSOT_CUSTOM_FIELD_LABEL},
    )
    for content_type in (device_ct, vm_ct, vminterface_ct, ipaddress_ct):
        custom_field.content_types.add(content_type)
    custom_field.type = CustomFieldTypeChoices.TYPE_DATETIME
    custom_field.save()

    # Links each VM to its host node Device (Nautobot's VirtualMachine has no host-Device FK).
    Relationship = apps.get_model("extras", "Relationship")
    Relationship.objects.get_or_create(
        label=HOST_RELATIONSHIP_LABEL,
        defaults={
            "key": HOST_RELATIONSHIP_KEY,
            "type": RelationshipTypeChoices.TYPE_ONE_TO_MANY,
            "source_type": device_ct,
            "destination_type": vm_ct,
        },
    )

    # Node hardware/version detail stored on the node Device.
    node_hardware_fields = (
        (CustomFieldTypeChoices.TYPE_TEXT, NODE_PVE_VERSION_CF, "Proxmox VE Version"),
        (CustomFieldTypeChoices.TYPE_INTEGER, NODE_CPU_COUNT_CF, "Proxmox CPU Count"),
        (CustomFieldTypeChoices.TYPE_INTEGER, NODE_MEMORY_GB_CF, "Proxmox Memory (GB)"),
    )
    for cf_type, cf_key, cf_label in node_hardware_fields:
        hardware_cf, _ = CustomField.objects.get_or_create(
            key=cf_key,
            defaults={"type": cf_type, "label": cf_label},
        )
        hardware_cf.content_types.add(device_ct)
        hardware_cf.type = cf_type
        hardware_cf.save()

    ClusterType.objects.get_or_create(name=CLUSTER_TYPE_NAME)

    # Node-as-Device prerequisites: Manufacturer, DeviceType, Role, LocationType, Location.
    manufacturer, _ = Manufacturer.objects.get_or_create(name=NODE_MANUFACTURER_NAME)
    DeviceType.objects.get_or_create(manufacturer=manufacturer, model=NODE_DEVICE_TYPE_NAME)

    node_role, _ = Role.objects.get_or_create(name=NODE_DEVICE_ROLE_NAME)
    node_role.content_types.add(device_ct)

    location_type, _ = LocationType.objects.get_or_create(name="Proxmox VE Location")
    location_type.content_types.add(device_ct)

    active_status.content_types.add(ContentType.objects.get_for_model(Location))
    active_status.content_types.add(device_ct)
    Location.objects.get_or_create(
        name=NODE_LOCATION_NAME,
        defaults={"location_type": location_type, "status": active_status},
    )


def create_default_proxmox_config(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create the default Proxmox VE config, SecretsGroup, and ExternalIntegration.

    Skipped entirely when ``proxmox_create_default_secrets`` is disabled in PLUGINS_CONFIG — without
    the default Secrets/SecretsGroup there is nothing for the default ExternalIntegration and config
    to reference, so operators managing those objects themselves opt out of the whole bootstrap.
    """
    if not config.get("proxmox_create_default_secrets", True):
        return

    SSOTProxmoxConfig = apps.get_model("nautobot_ssot", "SSOTProxmoxConfig")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    SecretsGroupAssociation = apps.get_model("extras", "SecretsGroupAssociation")
    Tag = apps.get_model("extras", "Tag")
    Role = apps.get_model("extras", "Role")
    ClusterType = apps.get_model("virtualization", "ClusterType")
    DeviceType = apps.get_model("dcim", "DeviceType")
    Location = apps.get_model("dcim", "Location")

    # nautobot_database_ready_callback (connected before this receiver in register_signals()) has
    # already created all of these — a strict .get() is safe and appropriately loud if that ordering
    # is ever wrong.
    default_ssot_tag = Tag.objects.get(name=SSOT_TAG_NAME)
    default_cluster_type = ClusterType.objects.get(name=CLUSTER_TYPE_NAME)
    default_device_role = Role.objects.get(name=NODE_DEVICE_ROLE_NAME)
    default_device_type = DeviceType.objects.get(model=NODE_DEVICE_TYPE_NAME)
    default_location = Location.objects.get(name=NODE_LOCATION_NAME)

    secrets_group, _ = SecretsGroup.objects.get_or_create(name="ProxmoxSSOTDefaultSecretGroup")
    proxmox_token_id, _ = Secret.objects.get_or_create(
        name="Proxmox Token ID - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_ID"},
        },
    )
    proxmox_token_secret, _ = Secret.objects.get_or_create(
        name="Proxmox Token Secret - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET"},
        },
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={"secret": proxmox_token_id},
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        defaults={"secret": proxmox_token_secret},
    )

    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="DefaultProxmoxInstance",
        defaults={
            "remote_url": "https://replace.me.local:8006",
            "secrets_group": secrets_group,
            "verify_ssl": False,
            "timeout": 30,
        },
    )

    if not SSOTProxmoxConfig.objects.exists():
        SSOTProxmoxConfig.objects.create(
            name="ProxmoxConfigDefault",
            description="Auto-generated default configuration.",
            proxmox_instance=external_integration,
            enable_sync_to_nautobot=True,
            job_enabled=True,
            default_ssot_tag=default_ssot_tag,
            default_cluster_type=default_cluster_type,
            default_device_role=default_device_role,
            default_device_type=default_device_type,
            default_location=default_location,
        )
