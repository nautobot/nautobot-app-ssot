"""Unit tests for Nautobot IPAM model CRUD functions."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.meraki.diffsync.models.nautobot import NautobotIPAddress, NautobotPrefix


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotPrefix(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotPrefix class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure common variables and objects for tests."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        self.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=self.status_active)[
            0
        ]
        self.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=self.status_active
        )[0]
        self.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        self.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        self.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        self.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.adapter = Adapter()
        self.adapter.namespace_map = {"Test": self.test_ns.id, "Update": self.update_site.id}
        self.adapter.site_map = {"Test": self.test_site, "Update": self.update_site}
        self.adapter.tenant_map = {"Test": self.test_tenant.id, "Update": self.update_tenant.id}
        self.adapter.status_map = {"Active": self.status_active.id}
        self.adapter.prefix_map = {}
        self.adapter.objects_to_create = {"prefixes": []}
        self.adapter.objects_to_delete = {"prefixes": []}

    def test_create(self):
        """Validate the NautobotPrefix create() method creates a Prefix."""
        self.prefix.delete()
        ids = {"prefix": "10.0.0.0/24", "namespace": "Test"}
        attrs = {"tenant": "Test"}
        result = NautobotPrefix.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotPrefix)
        self.assertEqual(len(self.adapter.objects_to_create["prefixes"]), 1)
        subnet = self.adapter.objects_to_create["prefixes"][0]
        self.assertEqual(str(subnet.prefix), ids["prefix"])
        self.assertEqual(self.adapter.prefix_map[ids["prefix"]], subnet.id)
        self.assertEqual(subnet.custom_field_data["system_of_record"], "Meraki SSoT")

    def test_update(self):
        """Validate the NautobotPrefix update() method updates a Prefix."""
        test_pf = NautobotPrefix(
            prefix="10.0.0.0/24",
            namespace="Test",
            tenant="Test",
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        update_attrs = {"tenant": "Update"}
        actual = NautobotPrefix.update(self=test_pf, attrs=update_attrs)
        self.prefix.refresh_from_db()
        self.assertEqual(self.prefix.tenant, self.update_tenant)
        self.assertEqual(actual, test_pf)

    @patch("nautobot_ssot.integrations.meraki.diffsync.models.nautobot.OrmPrefix.objects.get")
    def test_delete(self, mock_prefix):
        """Validate the NautobotPrefix delete() deletes a Prefix."""
        test_pf = NautobotPrefix(
            prefix="10.0.0.0/24",
            namespace="Test",
            tenant="Test",
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        mock_prefix.return_value = self.prefix
        test_pf.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["prefixes"][0].id, self.prefix.id)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotIPAddress(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotIPAddress class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure common variables and objects for tests."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        self.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=self.status_active)[
            0
        ]
        self.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=self.status_active
        )[0]
        self.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        self.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        self.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        self.prefix = Prefix(
            prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.adapter = Adapter()
        self.adapter.job = MagicMock()
        self.adapter.job.debug = True
        self.adapter.job.logger = MagicMock()
        self.adapter.job.logger.debug = MagicMock()
        self.adapter.job.logger.error = MagicMock()
        self.adapter.namespace_map = {"Test": self.test_ns.id, "Update": self.update_site.id}
        self.adapter.site_map = {"Test": self.test_site, "Update": self.update_site}
        self.adapter.tenant_map = {"Test": self.test_tenant.id, "Update": self.update_tenant.id}
        self.adapter.status_map = {"Active": self.status_active.id}
        self.adapter.ipaddr_map = {}
        self.adapter.prefix_map = {"10.0.0.0/24": self.prefix.id}
        self.adapter.objects_to_create = {"ipaddrs": [], "ipaddrs-to-prefixes": [], "prefixes": []}
        self.adapter.objects_to_delete = {"ipaddrs": []}
        self.test_ipaddr = IPAddress(
            address="10.0.0.1/24", parent=self.prefix, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ip = NautobotIPAddress(
            host="10.0.0.1",
            mask_length=24,
            prefix="10.0.0.0/24",
            tenant="Test",
            uuid=self.test_ipaddr.id,
        )
        self.test_ip.adapter = self.adapter

    def test_create(self):
        """Validate the NautobotAddress create() method creates an IPAddress."""
        self.test_ipaddr.delete()
        ids = {"host": "10.0.0.1", "tenant": "Test"}
        attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        result = NautobotIPAddress.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotIPAddress)
        self.assertEqual(len(self.adapter.objects_to_create["ipaddrs"]), 1)
        ipaddr = self.adapter.objects_to_create["ipaddrs"][0]
        self.assertEqual(str(ipaddr.host), ids["host"])
        self.assertEqual(ipaddr.mask_length, attrs["mask_length"])
        self.assertEqual(self.adapter.objects_to_create["ipaddrs-to-prefixes"][0], (ipaddr, self.prefix.id))
        self.assertEqual(self.adapter.ipaddr_map["Test"][ids["host"]], ipaddr.id)

    def test_update_mask_length(self):
        """Validate the NautobotAddress update() method updates an IPAddress mask length."""
        self.prefix.validated_save()
        self.test_ipaddr.validated_save()
        update_attrs = {"mask_length": 32}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.adapter.job.logger.debug.assert_called_once_with(
            ("Updating IPAddress 10.0.0.1/24 in Nautobot with {'mask_length': 32}.")
        )
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.mask_length, 32)
        self.assertIsInstance(actual, NautobotIPAddress)

    def test_update_to_existing_prefix(self):
        """Validate the NautobotAddress update() method updates an IPAddress to an existing prefix."""
        host_prefix = Prefix.objects.create(
            prefix="10.0.0.1/32", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.address = "10.0.0.1/32"
        self.test_ipaddr.parent = host_prefix
        self.test_ipaddr.validated_save()
        self.prefix.validated_save()
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.adapter.job.logger.debug.assert_called_once_with(
            "Updating IPAddress 10.0.0.1/32 in Nautobot with {'mask_length': 24, 'prefix': '10.0.0.0/24'}."
        )
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.parent.prefix, self.prefix.prefix)
        self.assertEqual(self.test_ipaddr.parent.type, "pool")
        self.assertIsInstance(actual, NautobotIPAddress)

    def test_update_to_new_prefix(self):
        """Validate the NautobotAddress update() method updates an IPAddress to a new prefix."""
        host_prefix = Prefix.objects.create(
            prefix="10.0.0.1/32", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.address = "10.0.0.1/32"
        self.test_ipaddr.mask_length = 32
        self.test_ipaddr.parent = host_prefix
        self.test_ipaddr.validated_save()
        self.prefix.delete()
        Prefix.objects.create(
            prefix="0.0.0.0/0", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        net_pf = Prefix(
            prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.adapter.prefix_map = {"10.0.0.0/24": net_pf.id}
        self.adapter.objects_to_create["prefixes"] = [net_pf]
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsInstance(actual, NautobotIPAddress)
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.parent.type, "pool")
        self.assertEqual(self.test_ipaddr.parent.prefix, net_pf.prefix)

    def test_update_to_missing_prefix(self):
        """Validate the NautobotAddress update() method handles a missing prefix."""
        self.prefix.delete()
        global_pf = Prefix.objects.create(
            prefix="0.0.0.0/0", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.parent = global_pf
        self.test_ipaddr.validated_save()
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsNone(actual)
        self.adapter.job.logger.error.assert_called_once_with("New parent Prefix 10.0.0.0/24 not found.")

    def test_update_to_prefix_missing_from_map(self):
        """Validate the NautobotAddress update() method handles a prefix missing from the prefix_map."""
        self.prefix.validated_save()
        self.test_ipaddr.validated_save()
        update_attrs = {"prefix": "10.100.0.0/8", "mask_length": 24}
        self.adapter.prefix_map = {}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsNone(actual)
        self.adapter.job.logger.error.assert_called_once_with("Prefix 10.100.0.0/8 not found in Nautobot.")
