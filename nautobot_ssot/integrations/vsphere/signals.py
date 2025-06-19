# pylint: disable=too-many-locals
# pylint: disable=duplicate-code
# pylint: disable=invalid-name

"""Signal handlers for nautobot_ssot_vsphere."""

from django.conf import settings
from nautobot.core.choices import ColorChoices
from nautobot.core.signals import nautobot_database_ready
from nautobot.extras.choices import (
    CustomFieldTypeChoices,
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)

config = settings.PLUGINS_CONFIG["nautobot_ssot"]


def register_signals(sender):
    """Register signals for vSphere integration."""
    nautobot_database_ready.connect(nautobot_database_ready_callback, sender=sender)
    nautobot_database_ready.connect(create_default_vsphere_config, sender=sender)


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create Tag and CustomField to note System of Record for SSoT."""
    Tag = apps.get_model("extras", "Tag")
    ClusterType = apps.get_model("virtualization", "ClusterType")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    VMInterface = apps.get_model("virtualization", "VMInterface")
    IPAddress = apps.get_model("ipam", "IPAddress")
    Status = apps.get_model("extras", "Status")
    CustomField = apps.get_model("extras", "CustomField")
    ContentType = apps.get_model("contenttypes", "ContentType")

    status, _ = Status.objects.get_or_create(name="Suspended", description="Machine is in a suspended state")
    status.content_types.add(ContentType.objects.get_for_model(VirtualMachine))
    status.save()

    tag_sync_from_vsphere, _ = Tag.objects.get_or_create(
        name="SSoT Synced from vSphere",
        defaults={
            "name": "SSoT Synced from vSphere",
            "description": "Object synced at some point from VMWare vSphere to Nautobot",
            "color": ColorChoices.COLOR_GREEN,
        },
    )
    for model in [VirtualMachine, VMInterface, IPAddress]:
        tag_sync_from_vsphere.content_types.add(ContentType.objects.get_for_model(model))

    custom_field, _ = CustomField.objects.get_or_create(
        type=CustomFieldTypeChoices.TYPE_DATE,
        key="last_synced_from_vsphere_on",
        defaults={
            "label": "Last synced from vSphere on",
        },
    )

    synced_from_models = [
        IPAddress,
        VirtualMachine,
        VMInterface,
    ]
    for model in synced_from_models:
        custom_field.content_types.add(ContentType.objects.get_for_model(model))
    custom_field.save()

    ClusterType.objects.get_or_create(name="VMWare vSphere")


def create_default_vsphere_config(sender, *, apps, **kwargs):  # pylint: disable=unused-argument
    """Create default vSphere config."""
    SSOTvSphereConfig = apps.get_model("nautobot_ssot", "SSOTvSphereConfig")
    VirtualMachine = apps.get_model("virtualization", "VirtualMachine")
    VMInterface = apps.get_model("virtualization", "VMInterface")
    Status = apps.get_model("extras", "Status")
    ExternalIntegration = apps.get_model("extras", "ExternalIntegration")
    Secret = apps.get_model("extras", "Secret")
    SecretsGroup = apps.get_model("extras", "SecretsGroup")
    SecretsGroupAssociation = apps.get_model("extras", "SecretsGroupAssociation")
    ContentType = apps.get_model("contenttypes", "ContentType")

    default_status, _ = Status.objects.get_or_create(name="Active")
    suspended_status, _ = Status.objects.get_or_create(name="Suspended")
    for model in [VirtualMachine, VMInterface]:
        default_status.content_types.add(ContentType.objects.get_for_model(model))
        suspended_status.content_types.add(ContentType.objects.get_for_model(model))

    secrets_group, _ = SecretsGroup.objects.get_or_create(name="vSphereSSOTDefaultSecretGroup")
    vsphere_username, _ = Secret.objects.get_or_create(
        name="vSphere Username - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_USERNAME"},
        },
    )

    vsphere_password, _ = Secret.objects.get_or_create(
        name="vSphere Password - Default",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_PASSWORD"},
        },
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={"secret": vsphere_username},
    )

    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        defaults={"secret": vsphere_password},
    )

    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="DefaultvSphereInstance",
        defaults={
            "remote_url": "https://replace.me.local",
            "secrets_group": secrets_group,
            "verify_ssl": False,
            "timeout": 10,
        },
    )

    if not SSOTvSphereConfig.objects.exists():
        SSOTvSphereConfig.objects.create(
            name="vSphereConfigDefault",
            description="Auto-generated default configuration.",
            vsphere_instance=external_integration,
            enable_sync_to_nautobot=True,
            job_enabled=True,
        )
