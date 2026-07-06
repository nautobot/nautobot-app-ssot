# pylint: disable=R0801
"""Nautobot object fixtures and helpers for Proxmox VE integration tests."""

from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import (
    ExternalIntegration,
    Role,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
    Tag,
)
from nautobot.virtualization.models import ClusterType

from nautobot_ssot.integrations.proxmox.choices import PrimaryIpSortByChoices
from nautobot_ssot.integrations.proxmox.constants import (
    CLUSTER_TYPE_NAME,
    NODE_DEVICE_ROLE_NAME,
    NODE_DEVICE_TYPE_NAME,
    NODE_LOCATION_NAME,
    NODE_MANUFACTURER_NAME,
    SSOT_TAG_NAME,
)
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig

DEFAULT_VM_STATUS_MAP = {"running": "Active", "stopped": "Offline", "paused": "Suspended"}
DEFAULT_IP_STATUS_MAP = {"PREFERRED": "Active", "UNKNOWN": "Reserved"}


def create_default_proxmox_config(proxmox_url="https://pve.local:8006"):
    """Create a default SSOTProxmoxConfig (with SecretsGroup + ExternalIntegration) for testing."""
    secrets_group, _ = SecretsGroup.objects.get_or_create(name="ProxmoxSSOTUnitTesting")
    token_id, _ = Secret.objects.get_or_create(
        name="Proxmox Token ID - Unit Testing",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_ID"},
        },
    )
    token_secret, _ = Secret.objects.get_or_create(
        name="Proxmox Token Secret - Unit Testing",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET"},
        },
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={"secret": token_id},
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
        defaults={"secret": token_secret},
    )
    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="ProxmoxUnitTestingInstance",
        remote_url=proxmox_url,
        secrets_group=secrets_group,
        verify_ssl=False,
        timeout=30,
    )

    # Reuse the same canonical names nautobot_database_ready_callback creates (and that other tests in
    # this suite hardcode/expect), rather than inventing fixture-specific names — a mismatched marker
    # tag here previously caused the sync to try to delete the real marker tag as "not in source".
    ssot_tag, _ = Tag.objects.get_or_create(name=SSOT_TAG_NAME)
    cluster_type, _ = ClusterType.objects.get_or_create(name=CLUSTER_TYPE_NAME)
    location_type, _ = LocationType.objects.get_or_create(name="Proxmox VE Location")
    active_status, _ = Status.objects.get_or_create(name="Active")
    location, _ = Location.objects.get_or_create(
        name=NODE_LOCATION_NAME,
        defaults={"location_type": location_type, "status": active_status},
    )
    manufacturer, _ = Manufacturer.objects.get_or_create(name=NODE_MANUFACTURER_NAME)
    device_type, _ = DeviceType.objects.get_or_create(manufacturer=manufacturer, model=NODE_DEVICE_TYPE_NAME)
    device_role, _ = Role.objects.get_or_create(name=NODE_DEVICE_ROLE_NAME)

    config, _ = SSOTProxmoxConfig.objects.get_or_create(
        name="ProxmoxUnitTestConfig",
        defaults=dict(  # pylint: disable=use-dict-literal
            description="Unit Test Config.",
            proxmox_instance=external_integration,
            enable_sync_to_nautobot=True,
            use_clusters=True,
            sync_lxc=True,
            sync_nodes_as_devices=True,
            sync_proxmox_tags=True,
            default_vm_status_map=DEFAULT_VM_STATUS_MAP,
            default_ip_status_map=DEFAULT_IP_STATUS_MAP,
            primary_ip_sort_by=PrimaryIpSortByChoices.LOWEST,
            default_ignore_link_local=True,
            job_enabled=True,
            default_ssot_tag=ssot_tag,
            default_cluster_type=cluster_type,
            default_location=location,
            default_device_type=device_type,
            default_device_role=device_role,
        ),
    )
    return config


def _get_virtual_machine_dict(attrs):
    """Build the dict used to instantiate a Virtual Machine DiffSync model."""
    virtual_machine_dict = {
        "status__name": "Active",
        "vcpus": 4,
        "memory": 4096,
        "disk": 32,
        "cluster__name": "TestCluster",
        "host_device": None,
        "primary_ip4__host": None,
        "primary_ip6__host": None,
        "tags": [],
    }
    virtual_machine_dict.update(attrs)
    return virtual_machine_dict


def _get_device_interface_dict(attrs):
    """Build the dict used to instantiate a node DCIM Interface DiffSync model."""
    interface_dict = {
        "type": "1000base-t",
        "enabled": True,
        "status__name": "Active",
        "mtu": None,
        "bridge__name": None,
        "lag__name": None,
        "parent_interface__name": None,
    }
    interface_dict.update(attrs)
    return interface_dict


def _get_vm_interface_dict(attrs):
    """Build the dict used to instantiate a VMInterface DiffSync model."""
    vm_interface_dict = {
        "enabled": True,
        "status__name": "Active",
        "mac_address": "AA:BB:CC:DD:EE:FF",
    }
    vm_interface_dict.update(attrs)
    return vm_interface_dict
