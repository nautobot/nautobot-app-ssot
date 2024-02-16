# pylint: disable=R0801
"""vSphere Integration model tests."""

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

from nautobot_ssot.integrations.vsphere.choices import PrimaryIpSortByChoices
from nautobot_ssot.integrations.vsphere.models import SSOTvSphereConfig


@mock.patch.dict(
    os.environ,
    {
        "NAUTOBOT_SSOT_VSPHERE_USERNAME": "username",
        "NAUTOBOT_SSOT_VSPHERE_PASSWORD": "password",
    },
)
class SSOTvSphereConfigTestCase(TestCase):  # pylint: disable=too-many-public-methods
    """Tests for the SSOTvSphereConfig models."""

    def setUp(self):
        """Setup testing."""
        vm_status_map = {
            "POWERED_OFF": "Offline",
            "POWERED_ON": "Active",
            "SUSPENDED": "Suspended",
        }
        ip_status_map = {"PREFERRED": "Active", "UNKNOWN": "Reserved"}

        secrets_group, _ = SecretsGroup.objects.get_or_create(name="vSphereSSOTUnitTest")
        inf_username, _ = Secret.objects.get_or_create(
            name="vSphere Username - vSphereSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_USERNAME"},
            },
        )
        inf_password, _ = Secret.objects.get_or_create(
            name="vSphere Password - vSphereSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_VSPHERE_PASSWORD"},
            },
        )
        self.sg_username, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            defaults={
                "secret": inf_username,
            },
        )
        self.sg_password, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            defaults={
                "secret": inf_password,
            },
        )
        self.external_integration = ExternalIntegration.objects.create(
            name="vSphereModelUnitTestInstance",
            remote_url="https://vsphere.local",
            secrets_group=secrets_group,
            verify_ssl=True,
            timeout=60,
        )

        self.vsphere_config_dict = {
            "name": "vSphereModelUnitTestConfig",
            "description": "Unit Test Config",
            "vsphere_instance": self.external_integration,
            "enable_sync_to_nautobot": True,
            "default_vm_status_map": vm_status_map,
            "default_ip_status_map": ip_status_map,
            "default_vm_interface_map": vm_status_map,
            "primary_ip_sort_by": PrimaryIpSortByChoices.LOWEST,
            "default_ignore_link_local": True,
            "job_enabled": True,
        }

    def test_create_vsphere_config_required_fields_only(self):
        """Successfully create vSphere config with required fields only."""
        vsphere_cfg = SSOTvSphereConfig(
            name="vSphereModelUnitTestConfigReqOnly",
            vsphere_instance=self.external_integration,
        )
        vsphere_cfg.validated_save()

        vsphere_cfg_db = SSOTvSphereConfig.objects.get(name="vSphereModelUnitTestConfigReqOnly")

        self.assertEqual(vsphere_cfg_db.name, "vSphereModelUnitTestConfigReqOnly")
        self.assertEqual(vsphere_cfg_db.description, "")
        self.assertEqual(vsphere_cfg_db.vsphere_instance, self.external_integration)
        self.assertEqual(vsphere_cfg_db.enable_sync_to_nautobot, True)
        self.assertEqual(
            vsphere_cfg_db.default_vm_status_map,
            {
                "POWERED_OFF": "Offline",
                "POWERED_ON": "Active",
                "SUSPENDED": "Suspended",
            },
        )
        self.assertEqual(
            vsphere_cfg_db.default_ip_status_map,
            {"PREFERRED": "Active", "UNKNOWN": "Reserved"},
        )
        self.assertEqual(
            vsphere_cfg_db.default_vm_interface_map,
            {"NOT_CONNECTED": False, "CONNECTED": True},
        )
        self.assertEqual(vsphere_cfg_db.primary_ip_sort_by, PrimaryIpSortByChoices.LOWEST)
        self.assertEqual(vsphere_cfg_db.default_ignore_link_local, True)
        self.assertEqual(vsphere_cfg_db.job_enabled, False)

    def test_create_vsphere_config_all_fields(self):
        """Successfully create vSphere config with all field."""

        vsphere_cfg = SSOTvSphereConfig(
            name="vSphereModelUnitTestConfigAllFields",
            description="This is a test.",
            vsphere_instance=self.external_integration,
            enable_sync_to_nautobot=True,
            default_vm_status_map={
                "POWERED_OFF": "Offline",
                "POWERED_ON": "Active",
                "SUSPENDED": "Suspended",
            },
            default_ip_status_map={"PREFERRED": "Active", "UNKNOWN": "Reserved"},
            default_vm_interface_map={"NOT_CONNECTED": False, "CONNECTED": True},
            primary_ip_sort_by=PrimaryIpSortByChoices.LOWEST,
            default_ignore_link_local=True,
            job_enabled=True,
        )
        vsphere_cfg.validated_save()

        vsphere_cfg_db = SSOTvSphereConfig.objects.get(name="vSphereModelUnitTestConfigAllFields")

        self.assertEqual(vsphere_cfg_db.name, "vSphereModelUnitTestConfigAllFields")
        self.assertEqual(vsphere_cfg_db.description, "This is a test.")
        self.assertEqual(vsphere_cfg_db.vsphere_instance, self.external_integration)
        self.assertEqual(vsphere_cfg_db.enable_sync_to_nautobot, True)
        self.assertEqual(
            vsphere_cfg_db.default_vm_status_map,
            {
                "POWERED_OFF": "Offline",
                "POWERED_ON": "Active",
                "SUSPENDED": "Suspended",
            },
        )
        self.assertEqual(
            vsphere_cfg_db.default_ip_status_map,
            {"PREFERRED": "Active", "UNKNOWN": "Reserved"},
        )
        self.assertEqual(
            vsphere_cfg_db.default_vm_interface_map,
            {"NOT_CONNECTED": False, "CONNECTED": True},
        )
        self.assertEqual(vsphere_cfg_db.primary_ip_sort_by, PrimaryIpSortByChoices.LOWEST)
        self.assertEqual(vsphere_cfg_db.default_ignore_link_local, True)
        self.assertEqual(vsphere_cfg_db.job_enabled, True)

    def test_vsphere_default_vm_status_map_dict(self):
        """default_vm_status_map must be a dict."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_status_map"] = "This is a string."
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_status_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Virtual Machine status map must be a dict.",
        )

    def test_vsphere_default_vm_status_map_invalid_key_found(self):
        """Only keys allowed in a filter are `POWERED_OFF`, `POWERED_ON` and `SUSPENDED`."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_status_map"] = {
            "OFF": "Offline",
            "ON": "Active",
            "SUSPENDED": "Suspended",
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_status_map", failure_exception.exception.error_dict)
        self.assertIn(
            "Invalid keys found in the VM status map",
            failure_exception.exception.messages[0],
        )

    def test_vsphere_default_vm_status_map_no_powered_on_key(self):
        """default_vm_status_map filter must have a `POWERED_ON` key defined."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_status_map"] = {
            "POWERED_OFF": "Offline",
            "SUSPENDED": "Suspended",
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_status_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Virtual Machine Status map must have 'POWERED_ON' key defined.",
        )

    def test_vsphere_default_vm_status_map_invalid_type(self):
        """Key `POWERED_ON` must be a string."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_status_map"] = {
            "POWERED_OFF": "Offline",
            "POWERED_ON": 2,
            "SUSPENDED": "Suspended",
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_status_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Value of 'POWERED_ON' must be a string.",
        )

    def test_vsphere_default_vm_status_map_no_existing_status(self):
        """An existing status must already exist in Nautobot."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_status_map"] = {
            "POWERED_OFF": "NotReal",
            "POWERED_ON": "Fake",
            "SUSPENDED": "DoesntExist",
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
            self.assertIn("default_vm_status_map", failure_exception.exception.error_dict)
            self.assertEqual(
                failure_exception.exception.messages[0],
                "No existing status found for 'POWERED_OFF'.",
            )

    def test_vsphere_default_ip_status_map_dict(self):
        """default_ip_status_map must be a dict."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_ip_status_map"] = []
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_ip_status_map", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "IP status map must be a dict.")

    def test_vsphere_default_ip_status_map_invalid_key_found(self):
        """Only keys allowed in a filter are 'PREFFERED' and 'UNKNOWN'."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_ip_status_map"] = {"OFF": "Offline", "ON": "Active"}
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_ip_status_map", failure_exception.exception.error_dict)
        self.assertIn(
            "Invalid keys found in the IP status map",
            failure_exception.exception.messages[0],
        )

    def test_vsphere_default_ip_status_map_no_preferred_key(self):
        """default_ip_status_map filter must have a `PREFFERED` key defined."""
        Status.objects.get_or_create(name="unknown")
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_ip_status_map"] = {"UNKNOWN": "unknown"}
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_ip_status_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "IP status map must have 'PREFERRED' key defined.",
        )

    def test_vsphere_default_ip_status_map_invalid_type(self):
        """Key `PREFERRED` must be a string."""
        Status.objects.get_or_create(name="unknown")
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_ip_status_map"] = {"PREFERRED": 1, "UNKNOWN": "unknown"}
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_ip_status_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Value of 'PREFERRED' must be a string.",
        )

    def test_vsphere_default_vm_interface_map_dict(self):
        """default_vm_interface_map must be a dict."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_interface_map"] = []
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_interface_map", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Interface map must be a dict.")

    def test_vsphere_default_vm_interface_map_invalid_key_found(self):
        """Only keys allowed in a filter are 'CONNECTED' and 'NOT_CONNECTED'."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_interface_map"] = {
            "CON": "Offline",
            "NOT_CON": "Active",
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_interface_map", failure_exception.exception.error_dict)
        self.assertIn(
            "Invalid keys found in the Interface map",
            failure_exception.exception.messages[0],
        )

    def test_vsphere_default_vm_interface_map_no_powered_on_key(self):
        """default_vm_interface_map filter must have a `CONNECTED` key defined."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_interface_map"] = {"NOT_CONNECTED": True}
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_interface_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Interface map must have 'CONNECTED' key defined.",
        )

    def test_vsphere_default_vm_interface_map_invalid_type(self):
        """Key `CONNECTED` must be a boolean."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["default_vm_interface_map"] = {
            "CONNECTED": 3,
            "NOT_CONNECTED": True,
        }
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("default_vm_interface_map", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Value of 'CONNECTED' must be a boolean.",
        )

    def test_vsphere_instance_must_have_secrets_group(self):
        """External integration for vSphere instance must have secrets group assigned."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_dict["vsphere_instance"].secrets_group = None
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("vsphere_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "vSphere instance must have Secrets groups assigned.",
        )

    def test_vsphere_instance_must_have_secrets_rest_username(self):
        """Secrets associated with secret group used by vSphere Instance must be of correct type."""
        vsphere_dict = deepcopy(self.vsphere_config_dict)
        vsphere_config = SSOTvSphereConfig(**vsphere_dict)
        self.sg_username.secret_type = SecretsGroupSecretTypeChoices.TYPE_TOKEN
        self.sg_username.save()
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("vsphere_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Secrets group for the vSphere instance must have secret with type Username and access type REST.",
        )
        self.sg_username.secret_type = SecretsGroupSecretTypeChoices.TYPE_USERNAME
        self.sg_username.save()
        self.sg_password.access_type = SecretsGroupAccessTypeChoices.TYPE_CONSOLE
        self.sg_password.save()
        with self.assertRaises(ValidationError) as failure_exception:
            vsphere_config.full_clean()
        self.assertIn("vsphere_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Secrets group for the vSphere instance must have secret with type Password and access type REST.",
        )
        self.sg_password.access_type = SecretsGroupAccessTypeChoices.TYPE_REST
        self.sg_password.save()
