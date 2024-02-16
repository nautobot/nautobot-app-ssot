# pylint: disable=R0801
"""Nautobot Object Fixtures."""

import os

from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import (
    ExternalIntegration,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
)

from nautobot_ssot.integrations.vsphere.choices import PrimaryIpSortByChoices
from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig
from nautobot_ssot.integrations.vsphere.utilities import VsphereClient

LOCALHOST = os.environ.get("TEST_LOCALHOST_URL", "https://vcenter.local")
DEFAULT_VM_STATUS_MAP = {
    "POWERED_OFF": "Offline",
    "POWERED_ON": "Active",
    "SUSPENDED": "Suspended",
}
DEFAULT_IP_STATUS_MAP = {"PREFERRED": "Active", "UNKNOWN": "Reserved"}
DEFAULT_VM_INTERFACE_MAP = {"NOT_CONNECTED": False, "CONNECTED": True}
DEFAULT_PRIMARY_IP_SORT = "Lowest"
DEFAULT_IGNORE_LINK_LOCAL = True


def create_default_vsphere_config(vsphere_url="vcenter.local"):
    """Create default vSphere config for testing."""
    secrets_group, _ = SecretsGroup.objects.get_or_create(name="vSphereSSOTUnitTesting")
    vsphere_username, _ = Secret.objects.get_or_create(
        name="vSphere Username - Unit Testing",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_USERNAME"},
        },
    )
    vsphere_password, _ = Secret.objects.get_or_create(
        name="vSphere Password - Unit Testing",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_PASSWORD"},
        },
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={
            "secret": vsphere_username,
        },
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        defaults={
            "secret": vsphere_password,
        },
    )
    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="vSphereUnitTestingInstance",
        remote_url=vsphere_url,
        secrets_group=secrets_group,
        verify_ssl=True,
        timeout=60,
    )

    config, _ = SSOTvSphereConfig.objects.get_or_create(
        name="vSpherexUnitTestConfig",
        defaults=dict(  # pylint: disable=use-dict-literal
            description="Unit Test Config.",
            vsphere_instance=external_integration,
            enable_sync_to_nautobot=True,
            default_vm_status_map=DEFAULT_VM_STATUS_MAP,
            default_ip_status_map=DEFAULT_IP_STATUS_MAP,
            default_vm_interface_map=DEFAULT_VM_INTERFACE_MAP,
            primary_ip_sort_by=PrimaryIpSortByChoices.LOWEST,
            default_ignore_link_local=True,
            job_enabled=True,
        ),
    )

    return config


def localhost_client_vsphere(localhost_url):
    """Return InfobloxAPI client for testing."""
    return VsphereClient(  # nosec
        vsphere_uri=localhost_url,
        username="test-user",
        password="test-password",
        verify_ssl=False,
        vm_status_map=DEFAULT_VM_STATUS_MAP,
        ip_status_map=DEFAULT_IP_STATUS_MAP,
        vm_interface_map=DEFAULT_VM_INTERFACE_MAP,
        primary_ip_sort_by=DEFAULT_PRIMARY_IP_SORT,
        ignore_link_local=DEFAULT_IGNORE_LINK_LOCAL,
        debug=False,
    )
