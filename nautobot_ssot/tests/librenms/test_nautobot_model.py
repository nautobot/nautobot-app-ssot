"""Unit tests for the Nautobot-side LibreNMS DiffSync models (NautobotDevice) and helpers."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer
from nautobot.dcim.models import Location as ORMLocation
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import Namespace
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.diffsync.models.base import Device, Location
from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import NautobotDevice, ensure_ip_address
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataTarget


class TestNautobotDeviceLocationSync(TestCase):
    """Test that NautobotDevice.update() honors the sync_locations job flag for the location field."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up a Nautobot Device already assigned to a real Location, plus a second candidate Location."""
        super().setUp()
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.chicago = ORMLocation.objects.create(
            name="Chicago", location_type=self.site_type, status=self.active_status
        )
        self.catch_all = ORMLocation.objects.create(
            name="Catch-All", location_type=self.site_type, status=self.active_status
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.orm_device = ORMDevice.objects.create(
            name="test-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.chicago,
        )

        self.adapter = MagicMock(spec=Adapter)
        self.adapter.job = MagicMock()
        self.adapter.job.location_type = self.site_type
        self.adapter.job.debug = False
        self.adapter.tenant = None

        self.diffsync_device = NautobotDevice(
            name="test-device",
            location="Chicago",
            status="Active",
            device_type="Test Device Type",
            manufacturer="Generic",
            system_of_record="LibreNMS",
            uuid=self.orm_device.id,
        )
        self.diffsync_device.adapter = self.adapter

    def test_update_does_not_overwrite_location_when_sync_locations_false(self):
        """Reparented devices must not be moved back by a later sync when sync_locations is False."""
        self.adapter.job.sync_locations = False

        self.diffsync_device.update(attrs={"location": "Catch-All", "parent_location": None})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.location, self.chicago)

    def test_update_overwrites_location_when_sync_locations_true(self):
        """With sync_locations True, per-device location updates still apply."""
        self.adapter.job.sync_locations = True

        self.diffsync_device.update(attrs={"location": "Catch-All", "parent_location": None})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.location, self.catch_all)

    def test_create_assigns_location_regardless_of_sync_locations(self):
        """A brand-new device must still get a location even when sync_locations is False."""
        self.adapter.job.sync_locations = False

        ids = {"name": "new-device"}
        attrs = {
            "location": "Catch-All",
            "parent_location": None,
            "status": "Active",
            "device_type": "Test Device Type",
            "manufacturer": "Linux",
            "platform": "linux",
            "role": "Test Role",
            "serial_no": "SN123",
            "os_version": "1.0",
            "device_id": 1,
            "system_of_record": "LibreNMS",
        }

        NautobotDevice.create(self.adapter, ids, attrs)

        new_orm_device = ORMDevice.objects.get(name="new-device")
        self.assertEqual(new_orm_device.location, self.catch_all)


class TestNautobotDeviceUpdatePlatform(TestCase):
    """Test that NautobotDevice.update() can update os_version without a platform change (issue #1153)."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up a Nautobot Device that already has a Platform assigned."""
        super().setUp()
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        self.active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.site_type, _ = LocationType.objects.get_or_create(name="Site")
        self.site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.chicago = ORMLocation.objects.create(
            name="Chicago", location_type=self.site_type, status=self.active_status
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))
        self.platform, _ = ORMPlatform.objects.get_or_create(name="linux", defaults={"manufacturer": manufacturer})

        self.orm_device = ORMDevice.objects.create(
            name="test-device",
            device_type=device_type,
            status=self.active_status,
            role=role,
            location=self.chicago,
            platform=self.platform,
        )

        self.adapter = MagicMock(spec=Adapter)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.sync_locations = False
        self.adapter.tenant = None

        self.diffsync_device = NautobotDevice(
            name="test-device",
            location="Chicago",
            status="Active",
            device_type="Test Device Type",
            manufacturer="Generic",
            system_of_record="LibreNMS",
            uuid=self.orm_device.id,
        )
        self.diffsync_device.adapter = self.adapter

    def test_update_os_version_without_platform_does_not_raise(self):
        """Updating os_version alone must not raise UnboundLocalError for _platform."""
        self.diffsync_device.update(attrs={"os_version": "2.0"})

        self.orm_device.refresh_from_db()
        software_version = self.orm_device.software_version
        self.assertIsNotNone(software_version)
        self.assertEqual(software_version.platform, self.platform)
        self.assertEqual(software_version.version, "2.0")


class TestEnsureIPAddress(TestCase):
    """Test that ensure_ip_address works with and without a tenant selected on the job."""

    def test_no_tenant_uses_global_namespace(self):
        """A sync without a Tenant Filter must not crash and must use the Global namespace."""
        adapter = MagicMock()
        adapter.job.tenant = None

        ip_address = ensure_ip_address(ip_address="192.0.2.10/24", ip_prefix="192.0.2.0/24", adapter=adapter)

        self.assertEqual(str(ip_address.address), "192.0.2.10/24")
        self.assertEqual(ip_address.parent.namespace, Namespace.objects.get(name="Global"))

    def test_tenant_uses_tenant_named_namespace(self):
        """A sync with a Tenant Filter places IPs in a namespace named after the tenant."""
        tenant = Tenant.objects.create(name="Acme Corp")
        adapter = MagicMock()
        adapter.job.tenant = tenant

        ip_address = ensure_ip_address(ip_address="198.51.100.10/24", ip_prefix="198.51.100.0/24", adapter=adapter)

        self.assertEqual(str(ip_address.address), "198.51.100.10/24")
        self.assertEqual(ip_address.parent.namespace.name, "Acme Corp")


class StubAdapter(Adapter):
    """Minimal adapter for diffing the base DiffSync models."""

    location = Location
    device = Device

    top_level = ["location", "device"]


class TestTenantNotSynced(TestCase):
    """Tenant differences must not produce diffs; tenant is assigned only at create time."""

    device_kwargs = {
        "name": "device1",
        "location": "Site A",
        "status": "Active",
        "device_type": "Model X",
        "manufacturer": "Vendor",
        "system_of_record": "LibreNMS",
    }

    def test_device_tenant_mismatch_produces_no_diff(self):
        """A device with a tenant in Nautobot but none in LibreNMS must not show a perpetual diff."""
        source = StubAdapter()
        target = StubAdapter()
        source.add(Device(**self.device_kwargs, tenant=None))
        target.add(Device(**self.device_kwargs, tenant="Acme Corp"))

        diff = source.diff_to(target)

        self.assertFalse(diff.has_diffs(), f"Tenant mismatch must not generate a diff: {diff.str()}")

    def test_tenant_not_in_synced_attributes(self):
        """Tenant must not be declared as a synced attribute on any LibreNMS DiffSync model."""
        self.assertNotIn("tenant", Device._attributes)  # pylint: disable=protected-access
        self.assertNotIn("tenant", Location._attributes)  # pylint: disable=protected-access


class TestLibrenmsDataTargetTenant(TestCase):
    """Test tenant handling in the Nautobot to LibreNMS job."""

    @patch("nautobot_ssot.integrations.librenms.diffsync.adapters.nautobot.NautobotAdapter")
    def test_load_source_adapter_passes_tenant(self, mock_adapter):
        """The optional Tenant Filter must be passed through to the Nautobot adapter."""
        job = LibrenmsDataTarget()
        job.sync = None
        job.tenant = Tenant.objects.create(name="Acme Corp")

        job.load_source_adapter()

        mock_adapter.assert_called_once_with(job=job, sync=None, tenant=job.tenant)

    @patch("nautobot_ssot.integrations.librenms.diffsync.adapters.nautobot.NautobotAdapter")
    def test_load_source_adapter_without_tenant(self, mock_adapter):
        """The job must load cleanly when no tenant is selected."""
        job = LibrenmsDataTarget()
        job.sync = None
        job.tenant = None

        job.load_source_adapter()

        mock_adapter.assert_called_once_with(job=job, sync=None, tenant=None)
