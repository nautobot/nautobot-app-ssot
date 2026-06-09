"""Unit tests for Nautobot IPAM model CRUD functions."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.meraki.diffsync.models.nautobot import NautobotIPAddress, NautobotPrefix


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotPrefix(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotPrefix class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        cls.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=cls.status_active)[0]
        cls.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=cls.status_active
        )[0]
        cls.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        cls.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=cls.test_ns, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.adapter = Adapter()
        cls.adapter.namespace_map = {"Test": cls.test_ns.id, "Update": cls.update_site.id}
        cls.adapter.site_map = {"Test": cls.test_site, "Update": cls.update_site}
        cls.adapter.tenant_map = {"Test": cls.test_tenant.id, "Update": cls.update_tenant.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.prefix_map = {}
        cls.adapter.objects_to_create = {"prefixes": []}
        cls.adapter.objects_to_delete = {"prefixes": []}

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
class TestNautobotIPAddress(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotIPAddress class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        cls.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=cls.status_active)[0]
        cls.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=cls.status_active
        )[0]
        cls.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        cls.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.prefix = Prefix(
            prefix="10.0.0.0/24", namespace=cls.test_ns, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = True
        cls.adapter.job.logger = MagicMock()
        cls.adapter.job.logger.debug = MagicMock()
        cls.adapter.job.logger.error = MagicMock()
        cls.adapter.namespace_map = {"Test": cls.test_ns.id, "Update": cls.update_site.id}
        cls.adapter.site_map = {"Test": cls.test_site, "Update": cls.update_site}
        cls.adapter.tenant_map = {"Test": cls.test_tenant.id, "Update": cls.update_tenant.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.ipaddr_map = {}
        cls.adapter.prefix_map = {"10.0.0.0/24": cls.prefix.id}
        cls.adapter.objects_to_create = {"ipaddrs": [], "ipaddrs-to-prefixes": [], "prefixes": []}
        cls.adapter.objects_to_delete = {"ipaddrs": []}
        cls.test_ipaddr = IPAddress(
            address="10.0.0.1/24", parent=cls.prefix, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.test_ip = NautobotIPAddress(
            host="10.0.0.1",
            mask_length=24,
            prefix="10.0.0.0/24",
            tenant="Test",
            uuid=cls.test_ipaddr.id,
        )
        cls.test_ip.adapter = cls.adapter

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
