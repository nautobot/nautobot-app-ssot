# pylint: disable=R0801
"""Infoblox Integration model tests."""
import os
from copy import deepcopy
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.models import ExternalIntegration, Secret, SecretsGroup, SecretsGroupAssociation, Status

from nautobot_ssot.integrations.infoblox.choices import DNSRecordTypeChoices, FixedAddressTypeChoices
from nautobot_ssot.integrations.infoblox.models import SSOTInfobloxConfig


@mock.patch.dict(os.environ, {"INFOBLOX_USERNAME": "username", "INFOBLOX_PASSWORD": "password"})
class SSOTInfobloxConfigTestCase(TestCase):  # pylint: disable=too-many-public-methods
    """Tests for the HardwareLCM models."""

    def setUp(self):
        """Setup testing."""
        self.default_status, _ = Status.objects.get_or_create(name="Active")
        sync_filters = [{"network_view": "default"}]

        infoblox_request_timeout = 60
        secrets_group, _ = SecretsGroup.objects.get_or_create(name="InfobloxSSOTUnitTest")
        inf_username, _ = Secret.objects.get_or_create(
            name="Infoblox Username - InfobloxSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "INFOBLOX_USERNAME"},
            },
        )
        inf_password, _ = Secret.objects.get_or_create(
            name="Infoblox Password - InfobloxSSOTUnitTest",
            defaults={
                "provider": "environment-variable",
                "parameters": {"variable": "INFOBLOX_PASSWORD"},
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
            name="InfobloxModelUnitTestInstance",
            remote_url="https://infoblox..me.local",
            secrets_group=secrets_group,
            verify_ssl=True,
            timeout=infoblox_request_timeout,
        )

        self.infoblox_config_dict = {
            "name": "InfobloxModelUnitTestConfig",
            "description": "Unit Test Config",
            "default_status": self.default_status,
            "infoblox_wapi_version": "v2.12",
            "infoblox_instance": self.external_integration,
            "enable_sync_to_infoblox": True,
            "import_ip_addresses": True,
            "import_subnets": True,
            "import_vlan_views": True,
            "import_vlans": True,
            "import_ipv4": True,
            "import_ipv6": False,
            "job_enabled": True,
            "infoblox_sync_filters": sync_filters,
            "infoblox_dns_view_mapping": {"default": "default.default"},
            "cf_fields_ignore": {"extensible_attributes": [], "custom_fields": []},
            "fixed_address_type": FixedAddressTypeChoices.DONT_CREATE_RECORD,
            "dns_record_type": DNSRecordTypeChoices.HOST_RECORD,
        }

    def test_create_infoblox_config_required_fields_only(self):
        """Successfully create Infoblox config with required fields only."""
        inf_cfg = SSOTInfobloxConfig(
            name="InfobloxModelUnitTestConfigReqOnly",
            default_status=self.default_status,
            infoblox_instance=self.external_integration,
        )
        inf_cfg.validated_save()

        inf_cfg_db = SSOTInfobloxConfig.objects.get(name="InfobloxModelUnitTestConfigReqOnly")

        self.assertEqual(inf_cfg_db.name, "InfobloxModelUnitTestConfigReqOnly")
        self.assertEqual(inf_cfg_db.description, "")
        self.assertEqual(inf_cfg_db.default_status, self.default_status)
        self.assertEqual(inf_cfg_db.infoblox_instance, self.external_integration)
        self.assertEqual(inf_cfg_db.infoblox_wapi_version, "v2.12")
        self.assertEqual(inf_cfg_db.enable_sync_to_infoblox, False)
        self.assertEqual(inf_cfg_db.import_ip_addresses, False)
        self.assertEqual(inf_cfg_db.import_subnets, False)
        self.assertEqual(inf_cfg_db.import_vlan_views, False)
        self.assertEqual(inf_cfg_db.import_vlans, False)
        self.assertEqual(inf_cfg_db.infoblox_sync_filters, [{"network_view": "default"}])
        self.assertEqual(inf_cfg_db.infoblox_dns_view_mapping, {})
        self.assertEqual(inf_cfg_db.cf_fields_ignore, {"custom_fields": [], "extensible_attributes": []})
        self.assertEqual(inf_cfg_db.import_ipv4, True)
        self.assertEqual(inf_cfg_db.import_ipv6, False)
        self.assertEqual(inf_cfg_db.fixed_address_type, FixedAddressTypeChoices.DONT_CREATE_RECORD)
        self.assertEqual(inf_cfg_db.dns_record_type, DNSRecordTypeChoices.HOST_RECORD)
        self.assertEqual(inf_cfg_db.job_enabled, False)

    def test_create_infoblox_config_all_fields(self):
        """Successfully create Infoblox config with all field."""
        inf_cfg = SSOTInfobloxConfig(
            name="InfobloxModelUnitTestConfigAllFields",
            default_status=self.default_status,
            infoblox_instance=self.external_integration,
            infoblox_wapi_version="v2.12",
            enable_sync_to_infoblox=True,
            import_ip_addresses=True,
            import_subnets=True,
            import_vlan_views=True,
            import_vlans=True,
            import_ipv4=False,
            import_ipv6=True,
            job_enabled=True,
            infoblox_sync_filters=[{"network_view": "dev"}],
            infoblox_dns_view_mapping={"default": "default.default"},
            cf_fields_ignore={"extensible_attributes": ["aws_id"], "custom_fields": ["po_no"]},
            fixed_address_type=FixedAddressTypeChoices.MAC_ADDRESS,
            dns_record_type=DNSRecordTypeChoices.A_RECORD,
        )
        inf_cfg.validated_save()

        inf_cfg_db = SSOTInfobloxConfig.objects.get(name="InfobloxModelUnitTestConfigAllFields")

        self.assertEqual(inf_cfg_db.name, "InfobloxModelUnitTestConfigAllFields")
        self.assertEqual(inf_cfg_db.description, "")
        self.assertEqual(inf_cfg_db.default_status, self.default_status)
        self.assertEqual(inf_cfg_db.infoblox_instance, self.external_integration)
        self.assertEqual(inf_cfg_db.infoblox_wapi_version, "v2.12")
        self.assertEqual(inf_cfg_db.enable_sync_to_infoblox, True)
        self.assertEqual(inf_cfg_db.import_ip_addresses, True)
        self.assertEqual(inf_cfg_db.import_subnets, True)
        self.assertEqual(inf_cfg_db.import_vlan_views, True)
        self.assertEqual(inf_cfg_db.import_vlans, True)
        self.assertEqual(inf_cfg_db.infoblox_sync_filters, [{"network_view": "dev"}])
        self.assertEqual(inf_cfg_db.infoblox_dns_view_mapping, {"default": "default.default"})
        self.assertEqual(inf_cfg_db.cf_fields_ignore, {"extensible_attributes": ["aws_id"], "custom_fields": ["po_no"]})
        self.assertEqual(inf_cfg_db.import_ipv4, False)
        self.assertEqual(inf_cfg_db.import_ipv6, True)
        self.assertEqual(inf_cfg_db.fixed_address_type, FixedAddressTypeChoices.MAC_ADDRESS)
        self.assertEqual(inf_cfg_db.dns_record_type, DNSRecordTypeChoices.A_RECORD)
        self.assertEqual(inf_cfg_db.job_enabled, True)

    def test_infoblox_sync_filters_must_be_a_list(self):
        """infoblox_sync_filters must be a list."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = {"k": "v"}
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Sync filters must be a list.")

    def test_infoblox_sync_filters_filter_must_be_dict(self):
        """Individual filter in infoblox_sync_filters must be a dict."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [""]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Sync filter must be a dict.")

    def test_infoblox_sync_filters_invalid_key_found(self):
        """Only keys allowed in a filter are `network_view`, `prefixes_ipv4` and `prefixes_ipv6`."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"prefixes": [], "name": "myname", "network_view": "dev"}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertIn("Invalid keys found in the sync filter", failure_exception.exception.messages[0])

    def test_infoblox_sync_filters_no_network_view_key(self):
        """Prefix filter must have a `network_view` key defined."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"prefixes_ipv4": ["10.0.0.0/24"]}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Sync filter must have `network_view` key defined.")

    def test_infoblox_sync_filters_network_view_invalid_type(self):
        """Key `network_view` must be a string."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": []}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Value of the `network_view` key must be a string.")

    def test_infoblox_sync_filters_duplicate_network_view(self):
        """Duplicate values for `network_view` are not allowed."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev"}, {"network_view": "dev"}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Duplicate value for the `network_view` found: dev.")

    def test_infoblox_sync_filters_prefixes_ipv4_must_be_list(self):
        """Value of `prefixes_ipv4` key must be a list."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv4": ""}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Value of the `prefixes_ipv4` key must be a list.")

    def test_infoblox_sync_filters_prefixes_ipv4_must_not_be_an_empty_list(self):
        """Value of `prefixes_ipv4` key must not be an empty list."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv4": []}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0], "Value of the `prefixes_ipv4` key must not be an empty list."
        )

    def test_infoblox_sync_filters_prefixes_ipv4_must_have_prefix_length(self):
        """Prefix in `prefixes_ipv4` must have prefix length defined."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv4": ["10.0.0.0"]}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "IPv4 prefix must have a prefix length defined using `/` format: 10.0.0.0.",
        )

    def test_infoblox_sync_filters_prefixes_ipv4_must_be_valid_prefix(self):
        """Prefix in `prefixes_ipv4` must be valid."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv4": ["10.0.0/24"]}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertIn("IPv4 prefix parsing error", failure_exception.exception.messages[0])

    def test_infoblox_sync_filters_prefixes_ipv6_must_be_list(self):
        """Value of `prefixes_ipv6` key must be a list."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv6": ""}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "Value of the `prefixes_ipv6` key must be a list.")

    def test_infoblox_sync_filters_prefixes_ipv6_must_not_be_an_empty_list(self):
        """Value of `prefixes_ipv6` key must not be an empty list."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv6": []}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0], "Value of the `prefixes_ipv6` key must not be an empty list."
        )

    def test_infoblox_sync_filters_prefixes_ipv6_must_have_prefix_length(self):
        """Prefix in `prefixes_ipv6` must have prefix length defined."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv6": ["2001:5b0:4100::"]}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "IPv6 prefix must have a prefix length defined using `/` format: 2001:5b0:4100::.",
        )

    def test_infoblox_sync_filters_prefixes_ipv6_must_be_valid_prefix(self):
        """Prefix in `prefixes_ipv6` must be valid."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_sync_filters"] = [{"network_view": "dev", "prefixes_ipv6": ["2001::5b0:4100::/40"]}]
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_sync_filters", failure_exception.exception.error_dict)
        self.assertIn("IPv6 prefix parsing error", failure_exception.exception.messages[0])

    def test_infoblox_instance_must_have_secrets_group(self):
        """External integration for Infoblox instance must have secrets group assigned."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_instance"].secrets_group = None
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0], "Infoblox instance must have Secrets groups assigned."
        )

    def test_infoblox_instance_must_have_secrets_rest_username(self):
        """Secrets associated with secret group used by Infoblox Instance must be of correct type."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        self.sg_username.secret_type = SecretsGroupSecretTypeChoices.TYPE_TOKEN
        self.sg_username.save()
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Secrets group for the Infoblox instance must have secret with type Username and access type REST.",
        )
        self.sg_username.secret_type = SecretsGroupSecretTypeChoices.TYPE_USERNAME
        self.sg_username.save()
        self.sg_password.access_type = SecretsGroupAccessTypeChoices.TYPE_CONSOLE
        self.sg_password.save()
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_instance", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Secrets group for the Infoblox instance must have secret with type Password and access type REST.",
        )
        self.sg_password.access_type = SecretsGroupAccessTypeChoices.TYPE_REST
        self.sg_password.save()

    def test_infoblox_import_ip_at_least_one_chosen(self):
        """At least one of `import_ipv4` or `import_ipv6` must be selected."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["import_ipv4"] = False
        inf_dict["import_ipv6"] = False
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("import_ipv4", failure_exception.exception.error_dict)
        self.assertIn("import_ipv6", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.error_dict["import_ipv4"][0].message,
            "At least one of `import_ipv4` or `import_ipv6` must be set to True.",
        )
        self.assertEqual(
            failure_exception.exception.error_dict["import_ipv6"][0].message,
            "At least one of `import_ipv4` or `import_ipv6` must be set to True.",
        )

    def test_infoblox_infoblox_dns_view_mapping_must_be_dict(self):
        """Value of `infoblox_dns_view_mapping` key must be a dict."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["infoblox_dns_view_mapping"] = []
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("infoblox_dns_view_mapping", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "`infoblox_dns_view_mapping` must be a dictionary mapping network view names to dns view names.",
        )

    def test_infoblox_infoblox_cf_fields_ignore_must_be_dict(self):
        """Value of `cf_fields_ignore` key must be a dict."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["cf_fields_ignore"] = []
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("cf_fields_ignore", failure_exception.exception.error_dict)
        self.assertEqual(failure_exception.exception.messages[0], "`cf_fields_ignore` must be a dictionary.")

    def test_infoblox_infoblox_cf_fields_key_names_must_be_valid(self):
        """Only `extensible_attributes` and `custom_fields` keys are allowed in `cf_fields_ignore`."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["cf_fields_ignore"] = {"fields": []}
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("cf_fields_ignore", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0],
            "Invalid key name `fields`. Only `extensible_attributes` and `custom_fields` are allowed.",
        )

    def test_infoblox_infoblox_cf_fields_values_must_be_list_of_string(self):
        """`infoblox_cf_fields` key values must be list of strings."""
        inf_dict = deepcopy(self.infoblox_config_dict)
        inf_dict["cf_fields_ignore"] = {"extensible_attributes": ["ea1", 2]}
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("cf_fields_ignore", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0], "Value of key `extensible_attributes` must be a list of strings."
        )

        inf_dict["cf_fields_ignore"] = {"custom_fields": ["cf1", 2]}
        infoblox_config = SSOTInfobloxConfig(**inf_dict)
        with self.assertRaises(ValidationError) as failure_exception:
            infoblox_config.full_clean()
        self.assertIn("cf_fields_ignore", failure_exception.exception.error_dict)
        self.assertEqual(
            failure_exception.exception.messages[0], "Value of key `custom_fields` must be a list of strings."
        )
