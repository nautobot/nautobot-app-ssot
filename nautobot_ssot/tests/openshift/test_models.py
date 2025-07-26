# pylint: disable=R0801
"""OpenShift Integration model tests."""

import os
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.extras.models import Status

from nautobot_ssot.integrations.openshift.models import SSOTOpenshiftConfig


class SSOTOpenshiftConfigTestCase(TestCase):  # pylint: disable=too-many-public-methods
    """Tests for the SSOTOpenshiftConfig models."""

    def setUp(self):
        """Setup testing."""
        self.config_data = {
            "name": "Test OpenShift",
            "description": "Test OpenShift configuration",
            "url": "https://api.openshift.example.com:6443",
            "api_token": "test-token-12345",
            "verify_ssl": True,
            "sync_namespaces": True,
            "sync_nodes": True,
            "sync_containers": True,
            "sync_deployments": True,
            "sync_services": True,
            "sync_kubevirt_vms": True,
            "namespace_filter": "",
            "workload_types": "all",
        }

    def test_create_config_minimal(self):
        """Test creating config with minimal required fields."""
        minimal_config = {
            "name": "Minimal OpenShift",
            "url": "https://api.openshift.example.com:6443",
            "api_token": "test-token",
        }
        config = SSOTOpenshiftConfig(**minimal_config)
        config.clean()
        config.save()
        self.assertEqual(config.name, "Minimal OpenShift")
        self.assertEqual(config.url, "https://api.openshift.example.com:6443")
        self.assertTrue(config.verify_ssl)  # Default value
        self.assertTrue(config.sync_namespaces)  # Default value

    def test_create_config_full(self):
        """Test creating config with all fields."""
        config = SSOTOpenshiftConfig(**self.config_data)
        config.clean()
        config.save()
        self.assertEqual(config.name, "Test OpenShift")
        self.assertEqual(config.description, "Test OpenShift configuration")
        self.assertTrue(config.sync_kubevirt_vms)

    def test_config_str_representation(self):
        """Test string representation of config."""
        config = SSOTOpenshiftConfig(**self.config_data)
        self.assertEqual(str(config), "Test OpenShift")

    def test_config_absolute_url(self):
        """Test get_absolute_url method."""
        config = SSOTOpenshiftConfig(**self.config_data)
        config.save()
        expected_url = f"/plugins/nautobot-ssot/openshift/config/{config.pk}/"
        self.assertEqual(config.get_absolute_url(), expected_url)

    def test_invalid_url_no_scheme(self):
        """Test validation error for URL without scheme."""
        invalid_config = deepcopy(self.config_data)
        invalid_config["url"] = "api.openshift.example.com:6443"
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("url", context.exception.error_dict)

    def test_invalid_url_wrong_scheme(self):
        """Test validation error for URL with wrong scheme."""
        invalid_config = deepcopy(self.config_data)
        invalid_config["url"] = "ftp://api.openshift.example.com:6443"
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("url", context.exception.error_dict)

    def test_empty_api_token(self):
        """Test validation error for empty API token."""
        invalid_config = deepcopy(self.config_data)
        invalid_config["api_token"] = ""
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("api_token", context.exception.error_dict)

    def test_no_sync_options_enabled(self):
        """Test validation error when no sync options are enabled."""
        invalid_config = deepcopy(self.config_data)
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
        invalid_config = deepcopy(self.config_data)
        invalid_config["workload_types"] = "vms"
        invalid_config["sync_kubevirt_vms"] = False
        config = SSOTOpenshiftConfig(**invalid_config)
        with self.assertRaises(ValidationError) as context:
            config.clean()
        self.assertIn("workload_types", context.exception.error_dict)

    def test_workload_types_choices(self):
        """Test workload_types field choices."""
        config = SSOTOpenshiftConfig(**self.config_data)
        
        # Test all valid choices
        for choice, _ in SSOTOpenshiftConfig._meta.get_field("workload_types").choices:
            config.workload_types = choice
            config.clean()  # Should not raise

    def test_namespace_filter_regex(self):
        """Test namespace filter accepts regex patterns."""
        config = SSOTOpenshiftConfig(**self.config_data)
        config.namespace_filter = "^prod-.*|^staging-.*"
        config.clean()
        config.save()
        self.assertEqual(config.namespace_filter, "^prod-.*|^staging-.*")

    def test_sync_options_independence(self):
        """Test that sync options can be enabled independently."""
        base_config = deepcopy(self.config_data)
        
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
            name="Default Test",
            url="https://api.test.com",
            api_token="token"
        )
        
        # Check defaults
        self.assertTrue(config.verify_ssl)
        self.assertTrue(config.sync_namespaces)
        self.assertTrue(config.sync_nodes)
        self.assertTrue(config.sync_containers)
        self.assertTrue(config.sync_deployments)
        self.assertTrue(config.sync_services)
        self.assertTrue(config.sync_kubevirt_vms)

    def test_workload_types_default(self):
        """Test default value for workload_types field."""
        config = SSOTOpenshiftConfig(
            name="Default Test",
            url="https://api.test.com",
            api_token="token"
        )
        self.assertEqual(config.workload_types, "all")

    def test_unique_name_constraint(self):
        """Test that name field must be unique."""
        config1 = SSOTOpenshiftConfig(**self.config_data)
        config1.save()
        
        config2 = SSOTOpenshiftConfig(**self.config_data)
        with self.assertRaises(ValidationError):
            config2.full_clean()

    def test_description_optional(self):
        """Test that description field is optional."""
        config_data = deepcopy(self.config_data)
        config_data["description"] = ""
        config = SSOTOpenshiftConfig(**config_data)
        config.clean()
        config.save()
        self.assertEqual(config.description, "")

    def test_ordering(self):
        """Test model ordering by name."""
        config1 = SSOTOpenshiftConfig(
            name="B OpenShift",
            url="https://b.test.com",
            api_token="token"
        )
        config1.save()
        
        config2 = SSOTOpenshiftConfig(
            name="A OpenShift",
            url="https://a.test.com",
            api_token="token"
        )
        config2.save()
        
        configs = list(SSOTOpenshiftConfig.objects.all())
        self.assertEqual(configs[0].name, "A OpenShift")
        self.assertEqual(configs[1].name, "B OpenShift") 