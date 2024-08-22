"""Signals triggered when Nautobot starts to perform certain actions."""

from django.conf import settings

from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices


try:
    import nautobot_device_lifecycle_mgmt  # noqa: F401 # pylint: disable=unused-import

    LIFECYCLE_MGMT = True
except ImportError:
    LIFECYCLE_MGMT = False


def register_signals(sender):
    """Register signals for IPFabric integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Adds OS Version and Physical Address CustomField to Devices and System of Record and Last Sync'd to Device, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
    CustomField = apps.get_model("extras", "CustomField")
    Device = apps.get_model("dcim", "Device")
    Manufacturer = apps.get_model("dcim", "Manufacturer")
    Platform = apps.get_model("dcim", "Platform")
    TenantGroup = apps.get_model("tenancy", "TenantGroup")
    Tenant = apps.get_model("tenancy", "Tenant")
    Team = apps.get_model("extras", "Team")
    Contact = apps.get_model("extras", "Contact")
    Location = apps.get_model("dcim", "Location")
    LocationType = apps.get_model("dcim", "LocationType")
    Namespace = apps.get_model("ipam", "Namespace")
    RIR = apps.get_model("ipam", "RiR")
    VLANGroup = apps.get_model("ipam", "VLANGroup")
    VLAN = apps.get_model("ipam", "VLAN")
    VRF = apps.get_model("ipam", "VRF")
    Prefix = apps.get_model("ipam", "Prefix")
    Provider = apps.get_model("circuits", "Provider")
    ProviderNetwork = apps.get_model("circuits", "ProviderNetwork")
    CircuitType = apps.get_model("circuits", "CircuitType")
    Circuit = apps.get_model("circuits", "Circuit")
    CircuitTermination = apps.get_model("circuits", "CircuitTermination")
    Tag = apps.get_model("extras", "Tag")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    DynamicGroup = apps.get_model("extras", "DynamicGroup")
    GitRepository = apps.get_model("extras", "GitRepository")
    Role = apps.get_model("extras", "Role")

    if LIFECYCLE_MGMT:
        SoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareLCM")
        SoftwareImageLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareImageLCM")
        ValidatedSoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "ValidatedSoftwareLCM")

    signal_to_model_mapping = {
        "device": Device,
        "manufacturer": Manufacturer,
        "platform": Platform,
        "role": Role,
        "tenant_group": TenantGroup,
        "tenant": Tenant,
        "team": Team,
        "contact": Contact,
        "location": Location,
        "location_type": LocationType,
        "namespace": Namespace,
        "rir": RIR,
        "vlan_group": VLANGroup,
        "vlan": VLAN,
        "vrf": VRF,
        "prefix": Prefix,
        "provider": Provider,
        "provider_network": ProviderNetwork,
        "circuit_type": CircuitType,
        "circuit": Circuit,
        "circuit_termination": CircuitTermination,
        "tag": Tag,
        "secret": Secret,
        "secrets_group": SecretsGroup,
        "dynamic_group": DynamicGroup,
        "git_repository": GitRepository,
    }

    if LIFECYCLE_MGMT:
        signal_to_model_mapping.update(
            {
                "software": SoftwareLCM,
                "software_image": SoftwareImageLCM,
                "validated_software": ValidatedSoftwareLCM,
            }
        )

    region = LocationType.objects.update_or_create(name="Region", defaults={"nestable": True})[0]
    site = LocationType.objects.update_or_create(name="Site", defaults={"nestable": False, "parent": region})[0]

    for ct in [Device, Prefix]:
        site.content_types.add(ContentType.objects.get_for_model(ct))

    sor_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_TEXT,
        "key": "system_of_record",
        "label": "System of Record",
    }
    sor_custom_field, _ = CustomField.objects.update_or_create(key=sor_cf_dict["key"], defaults=sor_cf_dict)
    sync_cf_dict = {
        "type": CustomFieldTypeChoices.TYPE_DATE,
        "key": "last_synced_from_sor",
        "label": "Last sync from System of Record",
    }
    sync_custom_field, _ = CustomField.objects.update_or_create(key=sync_cf_dict["key"], defaults=sync_cf_dict)

    models_to_sync = settings.PLUGINS_CONFIG["nautobot_ssot"]["bootstrap_models_to_sync"]
    no_cf = ["computed_field", "graph_ql_query"]
    for model in models_to_sync:
        if model not in no_cf and models_to_sync[model] is True:
            sor_custom_field.content_types.add(ContentType.objects.get_for_model(signal_to_model_mapping[model]))
            sync_custom_field.content_types.add(ContentType.objects.get_for_model(signal_to_model_mapping[model]))