"""Signals triggered when Nautobot starts to perform certain actions."""

from django.conf import settings
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import CustomFieldTypeChoices

from nautobot_ssot.utils import (
    core_supports_softwareversion,
    create_or_update_custom_field,
    dlm_supports_softwarelcm,
    validate_dlm_installed,
)


def register_signals(sender):
    """Register signals for IPFabric integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument, too-many-statements
    """Adds OS Version and Physical Address CustomField to Devices and System of Record and Last Sync'd to Device, and IPAddress.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name, too-many-locals
    ContentType = apps.get_model("contenttypes", "ContentType")
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
    ScheduledJob = apps.get_model("extras", "ScheduledJob")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    DynamicGroup = apps.get_model("extras", "DynamicGroup")
    GitRepository = apps.get_model("extras", "GitRepository")
    Role = apps.get_model("extras", "Role")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")

    signal_to_model_mapping = {
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
        "scheduled_job": ScheduledJob,
        "secret": Secret,
        "secrets_group": SecretsGroup,
        "dynamic_group": DynamicGroup,
        "git_repository": GitRepository,
        "external_integration": ExternalIntegration,
    }

    if core_supports_softwareversion():
        try:
            _SoftwareVersion = apps.get_model("dcim", "SoftwareVersion")
            signal_to_model_mapping["software"] = _SoftwareVersion
        except LookupError as err:
            print(f"Unable to find SoftwareVersion model from Nautobot Core. {err}")
        try:
            _SoftwareImageFile = apps.get_model("dcim", "SoftwareImageFile")
            signal_to_model_mapping["software_image"] = _SoftwareImageFile
        except LookupError as err:
            print(f"Unable to find SoftwareImageFile model from Nautobot Core. {err}")
        if validate_dlm_installed():
            try:
                ValidatedSoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "ValidatedSoftwareLCM")
                signal_to_model_mapping["validated_software"] = ValidatedSoftwareLCM
            except LookupError as err:
                print(f"Unable to find ValidatedSoftwareLCM model from Device Lifecycle Management App. {err}")
    elif dlm_supports_softwarelcm():
        try:
            SoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareLCM")
            signal_to_model_mapping["software"] = SoftwareLCM
        except LookupError as err:
            print(f"Unable to find SoftwareLCM model from Device Lifecycle Management App. {err}")
        try:
            SoftwareImageLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "SoftwareImageLCM")
            signal_to_model_mapping["software_image"] = SoftwareImageLCM
        except LookupError as err:
            print(f"Unable to find SoftwareImageLCM model from Device Lifecycle Management App. {err}")
        try:
            ValidatedSoftwareLCM = apps.get_model("nautobot_device_lifecycle_mgmt", "ValidatedSoftwareLCM")
            signal_to_model_mapping["validated_software"] = ValidatedSoftwareLCM
        except LookupError as err:
            print(f"Unable to find ValidatedSoftwareLCM model from Device Lifecycle Management App. {err}")

    sync_custom_field, _ = create_or_update_custom_field(
        apps,
        key="last_synced_from_sor",
        field_type=CustomFieldTypeChoices.TYPE_DATE,
        label="Last sync from System of Record",
    )
    sor_custom_field, _ = create_or_update_custom_field(
        apps,
        key="system_of_record",
        field_type=CustomFieldTypeChoices.TYPE_TEXT,
        label="System of Record",
    )

    models_to_sync = settings.PLUGINS_CONFIG.get("nautobot_ssot", {}).get("bootstrap_models_to_sync", {})
    no_cf = ["computed_field", "custom_field", "graph_ql_query", "software_image_file", "software_version"]
    try:
        for model in models_to_sync:
            if model not in no_cf and models_to_sync[model] is True:
                model_ct = ContentType.objects.get_for_model(signal_to_model_mapping[model])
                sor_custom_field.content_types.add(model_ct.id)
                sync_custom_field.content_types.add(model_ct.id)
    except Exception as e:
        print(f"Error occurred: {e}")
        raise
