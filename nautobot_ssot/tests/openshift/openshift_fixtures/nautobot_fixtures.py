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
    # Create secrets group for testing
    secrets_group, _ = SecretsGroup.objects.get_or_create(
        name="OpenShiftUnitTestSecretsGroup"
    )
    
    # Create secrets
    openshift_username, _ = Secret.objects.get_or_create(
        name="OpenShift Username - Unit Test",
        defaults={
            "provider": "environment-variable", 
            "parameters": {"variable": "TEST_OPENSHIFT_USERNAME"},
        },
    )
    openshift_token, _ = Secret.objects.get_or_create(
        name="OpenShift Token - Unit Test",
        defaults={
            "provider": "environment-variable",
            "parameters": {"variable": "TEST_OPENSHIFT_TOKEN"},
        },
    )
    
    # Create secrets group associations
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        defaults={"secret": openshift_username},
    )
    SecretsGroupAssociation.objects.get_or_create(
        secrets_group=secrets_group,
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        defaults={"secret": openshift_token},
    )
    
    # Create external integration
    external_integration, _ = ExternalIntegration.objects.get_or_create(
        name="OpenShift Unit Test Integration",
        defaults={
            "remote_url": openshift_url,
            "secrets_group": secrets_group,
            "verify_ssl": DEFAULT_VERIFY_SSL,
            "timeout": 60,
        },
    )
    
    # Create config
    config = SSOTOpenshiftConfig.objects.create(
        name="OpenShift - Unit Testing",
        description="Test OpenShift configuration",
        openshift_instance=external_integration,
        sync_namespaces=True,
        sync_nodes=True,
        sync_containers=True,
        sync_deployments=True,
        sync_services=True,
        sync_kubevirt_vms=True,
        namespace_filter="",
        workload_types=DEFAULT_WORKLOAD_TYPES,
        job_enabled=True,
        enable_sync_to_nautobot=True,
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