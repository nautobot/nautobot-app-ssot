"""Test the Nautobot CRUD functions for all DiffSync models."""

from unittest.mock import MagicMock

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, Location, LocationType
from nautobot.extras.models import Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.citrix_adm.diffsync.models.nautobot import NautobotAddress, NautobotDatacenter


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_citrix_adm": True}})
class TestNautobotDatacenter(TransactionTestCase):
    """Test the NautobotDatacenter class."""

    def setUp(self):
        """Configure shared objects."""
        super().setUp()
        self.adapter = Adapter()
        self.adapter.job = MagicMock()
        self.adapter.job.logger.warning = MagicMock()
        self.status_active = Status.objects.get(name="Active")
        self.test_dc = NautobotDatacenter(name="Test", region="", latitude=None, longitude=None, uuid=None)
        region_lt = LocationType.objects.get_or_create(name="Region")[0]
        self.global_region = Location.objects.create(name="Global", location_type=region_lt, status=self.status_active)
        site_lt = LocationType.objects.get_or_create(name="Site", parent=region_lt)[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Device))
        self.site_obj = Location.objects.create(
            name="HQ",
            location_type=site_lt,
            parent=self.global_region,
            status=self.status_active,
        )
        self.adapter.job.dc_loctype = site_lt
        self.adapter.job.parent_loc = None

    def test_create(self):
        """Validate the NautobotDatacenter create() method creates a Site."""
        self.site_obj.delete()
        ids = {"name": "HQ", "region": "Global"}
        attrs = {"latitude": 12.345, "longitude": -67.89}
        result = NautobotDatacenter.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotDatacenter)

        site_obj = Location.objects.get(name="HQ")
        self.assertEqual(site_obj.parent, self.global_region)
        self.assertEqual(float(site_obj.latitude), attrs["latitude"])
        self.assertEqual(float(site_obj.longitude), attrs["longitude"])

    def test_create_with_duplicate_site(self):
        """Validate the NautobotDatacenter create() method handling of duplicate Site."""
        ids = {"name": "HQ", "region": ""}
        attrs = {}
        NautobotDatacenter.create(self.adapter, ids, attrs)
        self.adapter.job.logger.warning.assert_called_with("Site HQ already exists so skipping creation.")

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"citrix_adm_update_sites": True}})
    def test_update(self):
        """Validate the NautobotDatacenter update() method updates a Site."""
        self.test_dc.uuid = self.site_obj.id
        update_attrs = {
            "latitude": 12.345,
            "longitude": -67.89,
        }
        actual = NautobotDatacenter.update(self=self.test_dc, attrs=update_attrs)
        self.site_obj.refresh_from_db()
        self.assertEqual(float(self.site_obj.latitude), update_attrs["latitude"])
        self.assertEqual(float(self.site_obj.longitude), update_attrs["longitude"])
        self.assertEqual(actual, self.test_dc)

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"citrix_adm_update_sites": False}})
    def test_update_setting_disabled(self):
        """Validate the NautobotDatacenter update() method doesn't update a Site if setting is False."""
        self.test_dc.adapter = MagicMock()
        self.test_dc.adapter.job = MagicMock()
        self.test_dc.adapter.job.logger.warning = MagicMock()
        NautobotDatacenter.update(self=self.test_dc, attrs={})
        self.test_dc.adapter.job.logger.warning.assert_called_once_with(
            "Update sites setting is disabled so skipping updating Test."
        )


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_citrix_adm": True}})
class TestNautobotAddress(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotAddress class."""

    def setUp(self):
        """Configure shared objects."""
        super().setUp()
        self.adapter = Adapter()
        self.adapter.job = MagicMock()
        self.adapter.job.logger.warning = MagicMock()
        self.status_active = Status.objects.get(name="Active")
        region_lt = LocationType.objects.get_or_create(name="Region")[0]
        self.global_region = Location.objects.create(name="Global", location_type=region_lt, status=self.status_active)
        site_lt = LocationType.objects.get_or_create(name="Site", parent=region_lt)[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Device))
        self.site_obj = Location.objects.create(
            name="HQ",
            location_type=site_lt,
            parent=self.global_region,
            status=self.status_active,
        )
        self.global_namespace = Namespace.objects.get_or_create(name="Global")[0]
        self.test_namespace = Namespace.objects.get_or_create(name="Test")[0]
        self.adapter.job.dc_loctype = site_lt
        self.adapter.job.parent_loc = None
        self.adapter.job.tenant = Tenant.objects.create(name="Test")
        self.test_prefix = Prefix.objects.create(
            prefix="10.1.1.0/24", namespace=self.test_namespace, status=self.status_active
        )
        self.update_ip_obj = IPAddress.objects.create(
            address="10.1.1.1/24", namespace=self.test_namespace, status=self.status_active
        )

    def test_create(self):
        """Validate the NautobotAddress create() method creates an IP Address."""
        self.update_ip_obj.delete()
        self.test_prefix.validated_save()
        ids = {"host_address": "10.1.1.1", "tenant": "Test"}
        attrs = {"mask_length": 24, "prefix": "10.1.1.0/24", "tags": ["test"]}
        result = NautobotAddress.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotAddress)
        addr_obj = IPAddress.objects.get(address="10.1.1.1/24")
        self.assertEqual(str(addr_obj.address).split("/", maxsplit=1)[0], ids["host_address"])
        self.assertEqual(addr_obj.tenant.name, ids["tenant"])
        self.assertEqual(addr_obj.tags.count(), 1)
        self.assertEqual(addr_obj.cf["system_of_record"], "Citrix ADM")

    def test_create_with_no_tenant(self):
        """Validate the NautobotAddress create() method creates an IP Address with no tenant."""
        Prefix.objects.create(prefix="192.168.1.0/29", namespace=self.global_namespace, status=self.status_active)
        ids = {"host_address": "192.168.1.1", "tenant": None}
        attrs = {"mask_length": 29, "prefix": "192.168.1.0/29", "tags": []}
        result = NautobotAddress.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotAddress)
        addr_obj = IPAddress.objects.get(address="192.168.1.1/29")
        self.assertIsNone(addr_obj.tenant)
        self.assertEqual(addr_obj.tags.count(), 0)

    def test_update(self):
        """Validate the NautobotAddress update() method updates an IP Address."""
        update_ip = NautobotAddress(
            host_address="10.1.1.1",
            mask_length=24,
            prefix="10.1.1.0/24",
            tenant="Test",
            tags=[],
            uuid=self.update_ip_obj.id,
        )
        self.test_prefix.validated_save()
        updated_parent = Prefix.objects.create(
            prefix="10.1.1.1/32", namespace=self.test_namespace, status=self.status_active
        )
        update_attrs = {
            "mask_length": 32,
            "prefix": "10.1.1.1/32",
            "tags": ["updated", "tags"],
        }
        results = update_ip.update(attrs=update_attrs)
        self.update_ip_obj.refresh_from_db()
        self.assertEqual(results, update_ip)
        self.assertEqual(self.update_ip_obj.mask_length, 32)
        self.assertEqual(self.update_ip_obj.parent, updated_parent)
        self.assertEqual(self.update_ip_obj.tags.count(), 2)

    def test_update_clears_tags(self):
        """Validate the NautobotAddress update() method clears tags when not provided."""
        update_ip = NautobotAddress(
            host_address="192.168.2.1",
            mask_length=28,
            prefix="192.168.2.0/28",
            tenant="Test",
            tags=[],
            uuid=self.update_ip_obj.id,
        )
        self.test_prefix.validated_save()
        update_tags = {"tags": []}
        results = update_ip.update(attrs=update_tags)
        self.update_ip_obj.refresh_from_db()
        self.assertEqual(results, update_ip)
        self.assertEqual(self.update_ip_obj.tags.count(), 0)
