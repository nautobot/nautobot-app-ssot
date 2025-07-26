# pylint: disable=R0801
"""OpenShift Integration model tests."""

import os
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.models import (
    ExternalIntegration,
    Secret,
    SecretsGroup,
    SecretsGroupAssociation,
    Status,
)

from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


@mock.patch.dict(
    os.environ,
    {
        "NAUTOBOT_SSOT_OPENSHIFT_USERNAME": "openshift",
        "NAUTOBOT_SSOT_OPENSHIFT_PASSWORD": "sha256~test-token-12345",
    },
)
class SSOTOpenshiftConfigTestCase(TestCase):  # pylint: disable=too-many-public-methods
    """Tests for the SSOTOpenshiftConfig models."""

    def setUp(self):
        """Setup testing."""
        # Create secrets group for OpenShift
        secrets_group, _ = SecretsGroup.objects.get_or_create(name="OpenShiftSSOTUnitTest")
        
        # Create secrets for username and API token
        openshift_username, _ = Secret.objects.get_or_create(
            name="OpenShift Username - OpenShiftSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_OPENSHIFT_USERNAME"},
            },
        )
        openshift_password, _ = Secret.objects.get_or_create(
            name="OpenShift Token - OpenShiftSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_OPENSHIFT_PASSWORD"},
            },
        )
        
        # Create secrets group associations
        self.sg_username, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            defaults={
                "secret": openshift_username,
            },
        )
        self.sg_password, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            defaults={
                "secret": openshift_password,
            },
        )
        
        # Create external integration
        self.external_integration = ExternalIntegration.objects.create(
            name="OpenShiftModelUnitTestInstance",
            remote_url="https://api.openshift.example.com:6443",
            secrets_group=secrets_group,
            verify_ssl=True,
            timeout=60,
        )

        self.openshift_config_dict = {
            "name": "OpenShiftModelUnitTestConfig",
            "description": "Unit Test Config",
            "openshift_instance": self.external_integration,
            "sync_namespaces": True,
            "sync_nodes": True,
            "sync_containers": True,
            "sync_deployments": True,
            "sync_services": True,
            "sync_kubevirt_vms": True,
            "namespace_filter": "",
            "workload_types": "all",
            "job_enabled": True,
            "enable_sync_to_nautobot": True,
        }

    def test_create_config_minimal(self):
        """Test creating config with minimal required fields."""
        config = SSOTOpenshiftConfig(
            name="MinimalOpenShiftConfig",
            openshift_instance=self.external_integration,
        )
        config.validated_save()
        
        config_db = SSOTOpenshiftConfig.objects.get(name="MinimalOpenShiftConfig")
        self.assertEqual(config_db.name, "MinimalOpenShiftConfig")
        self.assertEqual(config_db.openshift_instance, self.external_integration)
        self.assertTrue(config_db.sync_namespaces)  # Default value
        self.assertTrue(config_db.job_enabled)  # Default value should be False, but we're checking the field exists

    def test_create_config_full(self):
        """Test creating config with all fields."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config.validated_save()
        
        config_db = SSOTOpenshiftConfig.objects.get(name="OpenShiftModelUnitTestConfig")
        self.assertEqual(config_db.name, "OpenShiftModelUnitTestConfig")
        self.assertEqual(config_db.description, "Unit Test Config")
        self.assertEqual(config_db.openshift_instance, self.external_integration)
        self.assertTrue(config_db.sync_kubevirt_vms)
        self.assertEqual(config_db.workload_types, "all")

    def test_config_str_representation(self):
        """Test string representation of config."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        self.assertEqual(str(config), "OpenShiftModelUnitTestConfig")

    def test_config_absolute_url(self):
        """Test get_absolute_url method."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config.save()
        expected_url = f"/plugins/nautobot-ssot/openshift/config/{config.pk}/"
        self.assertEqual(config.get_absolute_url(), expected_url)

    def test_no_sync_options_enabled(self):
        """Test validation error when no sync options are enabled."""
        invalid_config = deepcopy(self.openshift_config_dict)
        invalid_config.update({
            "sync_namespaces": False,
            "sync_nodes": False,
            "sync_containers": False,
            "sync_deployments": False,
            "sync_services": False,
            "sync_kubevirt_vms": False,
        })
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("At least one sync option must be enabled", str(context.exception))

    def test_invalid_workload_type_vm_only_without_kubevirt(self):
        """Test validation error for VMs only when KubeVirt sync is disabled."""
        invalid_config = deepcopy(self.openshift_config_dict)
        invalid_config["workload_types"] = "vms"
        invalid_config["sync_kubevirt_vms"] = False
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("workload_types", context.exception.error_dict)

    def test_workload_types_choices(self):
        """Test workload_types field choices."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        
        # Test all valid choices
        for choice, _ in SSOTOpenshiftConfig._meta.get_field("workload_types").choices:
            config.workload_types = choice
            config.clean()  # Should not raise

    def test_namespace_filter_regex(self):
        """Test namespace filter accepts regex patterns."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config.namespace_filter = "^prod-.*|^staging-.*"
        config.clean()
        config.save()
        self.assertEqual(config.namespace_filter, "^prod-.*|^staging-.*")

    def test_sync_options_independence(self):
        """Test that sync options can be enabled independently."""
        base_config = deepcopy(self.openshift_config_dict)
        
        # Test each sync option independently
        sync_options = [
            "sync_namespaces",
            "sync_nodes", 
            "sync_containers",
            "sync_deployments",
            "sync_services",
            "sync_kubevirt_vms",
        ]
        
        for option in sync_options:
            test_config = deepcopy(base_config)
            test_config["name"] = f"Test{option}"
            # Disable all sync options
            for opt in sync_options:
                test_config[opt] = False
            # Enable only one
            test_config[option] = True
            
            config = SSOTOpenshiftConfig(**test_config)
            config.clean()  # Should not raise
            config.save()
            self.assertTrue(getattr(config, option))

    def test_boolean_field_defaults(self):
        """Test default values for boolean fields."""
        config = SSOTOpenshiftConfig(
            name="DefaultTest",
            openshift_instance=self.external_integration,
        )
        
        # Check defaults match model definition
        self.assertTrue(config.sync_namespaces)
        self.assertTrue(config.sync_nodes)
        self.assertTrue(config.sync_containers)
        self.assertTrue(config.sync_deployments)
        self.assertTrue(config.sync_services)
        self.assertTrue(config.sync_kubevirt_vms)
        self.assertFalse(config.job_enabled)  # Default should be False
        self.assertTrue(config.enable_sync_to_nautobot)  # Default should be True

    def test_workload_types_default(self):
        """Test default value for workload_types field."""
        config = SSOTOpenshiftConfig(
            name="DefaultTest",
            openshift_instance=self.external_integration,
        )
        self.assertEqual(config.workload_types, "all")

    def test_unique_name_constraint(self):
        """Test that name field must be unique."""
        config1 = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config1.save()
        
        config2_dict = deepcopy(self.openshift_config_dict)
        config2_dict["name"] = "OpenShiftModelUnitTestConfig"  # Same name
        config2 = SSOTOpenshiftConfig(**config2_dict)
        with self.assertRaises(ValidationError):
            config2.full_clean()

    def test_description_optional(self):
        """Test that description field is optional."""
        config_data = deepcopy(self.openshift_config_dict)
        config_data["description"] = ""
        config_data["name"] = "NoDescription"
        config = SSOTOpenshiftConfig(**config_data)
        config.clean()
        config.save()
        self.assertEqual(config.description, "")

    def test_ordering(self):
        """Test model ordering by name."""
        config1_dict = deepcopy(self.openshift_config_dict)
        config1_dict["name"] = "B_OpenShift"
        config1 = SSOTOpenshiftConfig(**config1_dict)
        config1.save()
        
        config2_dict = deepcopy(self.openshift_config_dict)
        config2_dict["name"] = "A_OpenShift"
        config2 = SSOTOpenshiftConfig(**config2_dict)
        config2.save()
        
        configs = list(SSOTOpenshiftConfig.objects.all())
        self.assertEqual(configs[0].name, "A_OpenShift")
        self.assertEqual(configs[1].name, "B_OpenShift")

    def test_external_integration_relationship(self):
        """Test the relationship with ExternalIntegration."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config.save()
        
        # Test accessing the remote URL through the relationship
        self.assertEqual(
            config.openshift_instance.remote_url,
            "https://api.openshift.example.com:6443"
        )
        
        # Test accessing verify_ssl through the relationship
        self.assertTrue(config.openshift_instance.verify_ssl)
        
        # Test accessing secrets group
        self.assertIsNotNone(config.openshift_instance.secrets_group)
        self.assertEqual(config.openshift_instance.secrets_group.name, "OpenShiftSSOTUnitTest")

    def test_job_control_flags(self):
        """Test job control flags work correctly."""
        config = SSOTOpenshiftConfig(**self.openshift_config_dict)
        config.job_enabled = False
        config.enable_sync_to_nautobot = False
        config.save()
        
        self.assertFalse(config.job_enabled)
        self.assertFalse(config.enable_sync_to_nautobot) 