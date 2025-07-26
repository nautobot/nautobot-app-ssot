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

from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig
from nautobot_ssot.integrations.openshift.utilities.openshift_client import OpenshiftClient

LOCALHOST = os.environ.get("TEST_OPENSHIFT_URL", "https://api.openshift.local:6443")
DEFAULT_WORKLOAD_TYPES = "all"
DEFAULT_VERIFY_SSL = False


def create_default_openshift_config(openshift_url=LOCALHOST):
    """Create default OpenShift config for testing."""
    config = SSOTOpenshiftConfig.objects.create(
        name="OpenShift - Unit Testing",
        description="Test OpenShift configuration",
        url=openshift_url,
        api_token="test-token-12345",
        verify_ssl=DEFAULT_VERIFY_SSL,
        sync_namespaces=True,
        sync_nodes=True,
        sync_containers=True,
        sync_deployments=True,
        sync_services=True,
        sync_kubevirt_vms=True,
        namespace_filter="",
        workload_types=DEFAULT_WORKLOAD_TYPES,
    )
    return config


def localhost_client_openshift(
    url=LOCALHOST,
    api_token="test-token-12345",
    verify_ssl=DEFAULT_VERIFY_SSL,
):
    """Mock OpenShift client for testing."""
    # We'll mock this in tests to avoid actual API calls
    return OpenshiftClient(url=url, api_token=api_token, verify_ssl=verify_ssl) 