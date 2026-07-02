# pylint: disable=R0801
"""Proxmox VE integration model tests."""

import os
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)
from nautobot.extras.management import populate_status_choices
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
from nautobot_ssot.integrations.proxmox.models import SSOTProxmoxConfig


@mock.patch.dict(
    os.environ,
    {
        "NAUTOBOT_SSOT_PROXMOX_TOKEN_ID": "svc@pve!nautobot",
        "NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET": "00000000-0000-0000-0000-000000000000",
    },
)
class SSOTProxmoxConfigTestCase(TestCase):  # pylint: disable=too-many-public-methods
    """Tests for the SSOTProxmoxConfig model."""

    @classmethod
    def setUpTestData(cls):
        """Set up data shared across tests."""
        populate_status_choices()
        Status.objects.get_or_create(name="Suspended")

        secrets_group, _ = SecretsGroup.objects.get_or_create(name="ProxmoxSSOTModelUnitTest")
        token_id, _ = Secret.objects.get_or_create(
            name="Proxmox Token ID - ProxmoxSSOTModelUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_ID"},
            },
        )
        token_secret, _ = Secret.objects.get_or_create(
            name="Proxmox Token Secret - ProxmoxSSOTModelUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "NAUTOBOT_SSOT_PROXMOX_TOKEN_SECRET"},
            },
        )
        cls.sg_token_id, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            defaults={"secret": token_id},
        )
        cls.sg_token_secret, _ = SecretsGroupAssociation.objects.get_or_create(
            secrets_group=secrets_group,
            access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
            defaults={"secret": token_secret},
        )
        cls.external_integration = ExternalIntegration.objects.create(
            name="ProxmoxModelUnitTestInstance",
            remote_url="https://pve.local:8006",
            secrets_group=secrets_group,
            verify_ssl=False,
            timeout=30,
        )

        cls.ssot_tag = Tag.objects.get_or_create(name="ProxmoxModelUnitTestTag")[0]
        cls.cluster_type = ClusterType.objects.get_or_create(name="ProxmoxModelUnitTestClusterType")[0]
        location_type, _ = LocationType.objects.get_or_create(name="ProxmoxModelUnitTestLocationType")
        active_status, _ = Status.objects.get_or_create(name="Active")
        cls.location = Location.objects.get_or_create(
            name="ProxmoxModelUnitTestLocation",
            defaults={"location_type": location_type, "status": active_status},
        )[0]
        manufacturer, _ = Manufacturer.objects.get_or_create(name="ProxmoxModelUnitTestManufacturer")
        cls.device_type = DeviceType.objects.get_or_create(
            manufacturer=manufacturer, model="ProxmoxModelUnitTestDeviceType"
        )[0]
        cls.device_role = Role.objects.get_or_create(name="ProxmoxModelUnitTestRole")[0]

        cls.proxmox_config_dict = {
            "name": "ProxmoxModelUnitTestConfig",
            "description": "Unit Test Config",
            "proxmox_instance": cls.external_integration,
            "enable_sync_to_nautobot": True,
            "default_vm_status_map": {"running": "Active", "stopped": "Offline"},
            "default_ip_status_map": {"PREFERRED": "Active", "UNKNOWN": "Reserved"},
            "primary_ip_sort_by": PrimaryIpSortByChoices.LOWEST,
            "default_ignore_link_local": True,
            "job_enabled": True,
            "default_ssot_tag": cls.ssot_tag,
            "default_cluster_type": cls.cluster_type,
            "default_location": cls.location,
            "default_device_type": cls.device_type,
            "default_device_role": cls.device_role,
        }

    def test_create_config_required_fields_only(self):
        """Create a config with only required fields (including the 5 required object references) and confirm defaults."""
        config = SSOTProxmoxConfig(
            name="ProxmoxReqOnly",
            proxmox_instance=self.external_integration,
            default_ssot_tag=self.ssot_tag,
            default_cluster_type=self.cluster_type,
            default_location=self.location,
            default_device_type=self.device_type,
            default_device_role=self.device_role,
        )
        config.validated_save()

        config_db = SSOTProxmoxConfig.objects.get(name="ProxmoxReqOnly")
        self.assertEqual(config_db.description, "")
        self.assertEqual(config_db.proxmox_instance, self.external_integration)
        self.assertTrue(config_db.enable_sync_to_nautobot)
        self.assertTrue(config_db.use_clusters)
        self.assertTrue(config_db.sync_lxc)
        self.assertTrue(config_db.sync_nodes_as_devices)
        self.assertEqual(
            config_db.default_vm_status_map,
            {"running": "Active", "stopped": "Offline", "paused": "Suspended"},
        )
        self.assertEqual(config_db.default_ip_status_map, {"PREFERRED": "Active", "UNKNOWN": "Reserved"})
        self.assertEqual(config_db.primary_ip_sort_by, PrimaryIpSortByChoices.LOWEST)
        self.assertFalse(config_db.job_enabled)
        # The 5 object-reference fields are required with no model-level default; confirm they persist.
        self.assertEqual(config_db.default_cluster_type, self.cluster_type)
        self.assertEqual(config_db.default_ssot_tag, self.ssot_tag)
        self.assertEqual(config_db.default_location, self.location)
        self.assertEqual(config_db.default_device_type, self.device_type)
        self.assertEqual(config_db.default_device_role, self.device_role)
        # The node interface type map defaults to the built-in mapping.
        self.assertEqual(config_db.default_node_interface_type_map["eth"], "1000base-t")
        self.assertEqual(config_db.default_node_interface_type_map["bond"], "lag")
        self.assertEqual(config_db.default_node_interface_type_map["bridge"], "bridge")
        self.assertEqual(config_db.default_node_interface_type_map["vlan"], "virtual")

    def test_default_node_interface_type_map_custom_value(self):
        """A custom node interface type map with valid keys/values is accepted and persisted."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["name"] = "ProxmoxCustomIfaceMap"
        config_dict["default_node_interface_type_map"] = {"eth": "10gbase-t", "bridge": "bridge"}
        config = SSOTProxmoxConfig(**config_dict)
        config.validated_save()
        config_db = SSOTProxmoxConfig.objects.get(name="ProxmoxCustomIfaceMap")
        self.assertEqual(config_db.default_node_interface_type_map, {"eth": "10gbase-t", "bridge": "bridge"})

    def test_default_node_interface_type_map_empty_allowed(self):
        """An empty node interface type map is allowed (the sync falls back to the default)."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["name"] = "ProxmoxEmptyIfaceMap"
        config_dict["default_node_interface_type_map"] = {}
        config = SSOTProxmoxConfig(**config_dict)
        config.full_clean()  # must not raise

    def test_default_node_interface_type_map_unknown_key(self):
        """Keys must be known Proxmox interface types."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_node_interface_type_map"] = {"wlan": "1000base-t"}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_node_interface_type_map", failure.exception.error_dict)
        self.assertIn("Unknown Proxmox interface type 'wlan'", failure.exception.messages[0])

    def test_default_node_interface_type_map_invalid_type(self):
        """Values must be valid Nautobot interface-type slugs."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_node_interface_type_map"] = {"eth": "not-a-real-type"}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_node_interface_type_map", failure.exception.error_dict)
        self.assertIn("not a valid Nautobot interface type", failure.exception.messages[0])

    def test_default_vm_status_map_must_be_dict(self):
        """default_vm_status_map must be a dict."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_vm_status_map"] = "not a dict"
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_vm_status_map", failure.exception.error_dict)
        self.assertEqual(failure.exception.messages[0], "Virtual Machine status map must be a dict.")

    def test_default_vm_status_map_not_empty(self):
        """An empty default_vm_status_map is rejected (field-level blank validation)."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_vm_status_map"] = {}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_vm_status_map", failure.exception.error_dict)

    def test_default_vm_status_map_value_must_be_string(self):
        """Values in default_vm_status_map must be strings."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_vm_status_map"] = {"running": 1}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_vm_status_map", failure.exception.error_dict)
        self.assertEqual(failure.exception.messages[0], "Value of 'running' must be a string.")

    def test_default_vm_status_map_status_must_exist(self):
        """Values in default_vm_status_map must reference an existing Status."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_vm_status_map"] = {"running": "DoesNotExist"}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_vm_status_map", failure.exception.error_dict)
        self.assertEqual(failure.exception.messages[0], "No existing status found for 'DoesNotExist'.")

    def test_default_ip_status_map_invalid_key(self):
        """default_ip_status_map only allows PREFERRED and UNKNOWN keys."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_ip_status_map"] = {"PREFERRED": "Active", "BOGUS": "Active"}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_ip_status_map", failure.exception.error_dict)
        self.assertIn("Invalid keys found in the IP status map", failure.exception.messages[0])

    def test_default_ip_status_map_missing_key(self):
        """default_ip_status_map must define PREFERRED and UNKNOWN."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["default_ip_status_map"] = {"PREFERRED": "Active"}
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("default_ip_status_map", failure.exception.error_dict)
        self.assertEqual(failure.exception.messages[0], "IP status map must have 'UNKNOWN' key defined.")

    def test_instance_must_have_secrets_group(self):
        """The proxmox_instance ExternalIntegration must have a SecretsGroup."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config_dict["proxmox_instance"].secrets_group = None
        config = SSOTProxmoxConfig(**config_dict)
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("proxmox_instance", failure.exception.error_dict)
        self.assertEqual(
            failure.exception.messages[0],
            "Proxmox VE instance must have Secrets group assigned.",
        )

    def test_instance_secrets_group_requires_rest_token(self):
        """SecretsGroup must expose a REST Token secret (the API token secret)."""
        config_dict = deepcopy(self.proxmox_config_dict)
        config = SSOTProxmoxConfig(**config_dict)
        self.sg_token_secret.secret_type = SecretsGroupSecretTypeChoices.TYPE_PASSWORD
        self.sg_token_secret.save()
        with self.assertRaises(ValidationError) as failure:
            config.full_clean()
        self.assertIn("proxmox_instance", failure.exception.error_dict)
        self.assertIn("Token", failure.exception.messages[0])
        self.sg_token_secret.secret_type = SecretsGroupSecretTypeChoices.TYPE_TOKEN
        self.sg_token_secret.save()
