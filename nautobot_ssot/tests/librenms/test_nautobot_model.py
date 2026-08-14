"""Unit tests for the Nautobot-side LibreNMS DiffSync models (NautobotDevice) and helpers."""

from inspect import signature
from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as ORMDevice
from nautobot.dcim.models import DeviceType, LocationType, Manufacturer
from nautobot.dcim.models import Location as ORMLocation
from nautobot.dcim.models import Platform as ORMPlatform
from nautobot.extras.models import Role, SecretsGroup, Status
from nautobot.ipam.models import Namespace
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import NautobotDevice, ensure_ip_address
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource, LibrenmsDataTarget


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
        self.adapter.job.device_secrets_group = None
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
        self.adapter.job.device_secrets_group = None
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


DEVICE_CREATE_IDS = {"name": "new-device"}
DEVICE_CREATE_ATTRS = {
    "location": "Chicago",
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


class TestNautobotDeviceSecretsGroup(TestCase):
    """Test that NautobotDevice assigns the device_secrets_group job var without clobbering existing groups."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up a Nautobot Device with no Secrets Group, plus two Secrets Groups to assign."""
        super().setUp()
        active_status, _ = Status.objects.get_or_create(name="Active")
        active_status.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        chicago = ORMLocation.objects.create(name="Chicago", location_type=site_type, status=active_status)

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Generic")
        device_type, _ = DeviceType.objects.get_or_create(model="Test Device Type", manufacturer=manufacturer)
        role, _ = Role.objects.get_or_create(name="Test Role")
        role.content_types.add(ContentType.objects.get_for_model(ORMDevice))

        self.job_secrets_group = SecretsGroup.objects.create(name="Device Credentials")
        self.existing_secrets_group = SecretsGroup.objects.create(name="Pre-Existing Credentials")

        self.orm_device = ORMDevice.objects.create(
            name="test-device",
            device_type=device_type,
            status=active_status,
            role=role,
            location=chicago,
        )

        self.adapter = MagicMock(spec=Adapter)
        self.adapter.job = MagicMock()
        self.adapter.job.location_type = site_type
        self.adapter.job.debug = False
        self.adapter.job.sync_locations = False
        self.adapter.job.device_secrets_group = None
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

    def test_create_assigns_secrets_group(self):
        """A created Device gets the Secrets Group selected on the job form."""
        self.adapter.job.device_secrets_group = self.job_secrets_group

        NautobotDevice.create(self.adapter, DEVICE_CREATE_IDS.copy(), DEVICE_CREATE_ATTRS.copy())

        new_orm_device = ORMDevice.objects.get(name="new-device")
        self.assertEqual(new_orm_device.secrets_group, self.job_secrets_group)

    def test_create_without_secrets_group(self):
        """Leaving the Secrets Group field blank must still create the Device."""
        self.adapter.job.device_secrets_group = None

        NautobotDevice.create(self.adapter, DEVICE_CREATE_IDS.copy(), DEVICE_CREATE_ATTRS.copy())

        new_orm_device = ORMDevice.objects.get(name="new-device")
        self.assertIsNone(new_orm_device.secrets_group)

    def test_update_backfills_secrets_group_when_unset(self):
        """A Device with no Secrets Group picks one up on update."""
        self.adapter.job.device_secrets_group = self.job_secrets_group

        self.diffsync_device.update(attrs={"serial_no": "SN999"})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.secrets_group, self.job_secrets_group)

    def test_update_does_not_clobber_existing_secrets_group(self):
        """A hand-assigned or onboarding-assigned Secrets Group survives later syncs."""
        self.orm_device.secrets_group = self.existing_secrets_group
        self.orm_device.validated_save()
        self.adapter.job.device_secrets_group = self.job_secrets_group

        self.diffsync_device.update(attrs={"serial_no": "SN999"})

        self.orm_device.refresh_from_db()
        self.assertEqual(self.orm_device.secrets_group, self.existing_secrets_group)

    def test_update_without_secrets_group_leaves_none(self):
        """An update with the form field blank must not raise and must leave the Device unchanged."""
        self.adapter.job.device_secrets_group = None

        self.diffsync_device.update(attrs={"serial_no": "SN999"})

        self.orm_device.refresh_from_db()
        self.assertIsNone(self.orm_device.secrets_group)
        self.assertEqual(self.orm_device.serial, "SN999")


class TestLibrenmsDataSourceSecretsGroupVar(TestCase):
    """Test the device_secrets_group job var stays optional and backwards compatible."""

    def test_device_secrets_group_var_is_optional(self):
        """The field must not be required, so existing scheduled jobs keep validating."""
        job_vars = LibrenmsDataSource._get_vars()  # pylint: disable=protected-access

        self.assertIn("device_secrets_group", job_vars)
        self.assertFalse(job_vars["device_secrets_group"].field_attrs.get("required"))

    def test_run_defaults_device_secrets_group_to_none(self):
        """Nautobot's deserialize_data only passes stored kwargs, so run() needs its own default.

        Without it, every ScheduledJob created before this field existed would raise
        TypeError: run() missing 1 required positional argument.
        """
        parameter = signature(LibrenmsDataSource.run).parameters["device_secrets_group"]

        self.assertIsNone(parameter.default)


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
