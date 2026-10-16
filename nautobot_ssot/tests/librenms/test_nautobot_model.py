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

from nautobot_ssot.integrations.librenms.diffsync.models.nautobot import (
    NautobotDevice,
    ensure_ip_address,
    ensure_platform,
)
from nautobot_ssot.integrations.librenms.jobs import LibrenmsDataSource, LibrenmsDataTarget
from nautobot_ssot.integrations.librenms.utils.nautobot import clear_network_driver_caches


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


class EnsurePlatformTestCase(TestCase):
    """Shared setup for the two `ensure_platform` modes."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()
        clear_network_driver_caches()
        self.addCleanup(clear_network_driver_caches)
        self.cisco, _ = Manufacturer.objects.get_or_create(name="Cisco")
        self.fortinet, _ = Manufacturer.objects.get_or_create(name="Fortinet")

    def _adapter(self, consolidated):
        """Build an adapter stub carrying the platform-naming mode."""
        adapter = MagicMock(spec=Adapter)
        adapter.job = MagicMock()
        adapter.job.debug = False
        adapter.consolidated_platforms = consolidated
        return adapter


class TestEnsurePlatformLegacyMode(EnsurePlatformTestCase):
    """Legacy mode must keep today's naming, byte for byte."""

    def test_creates_fqcn_named_platform_with_valid_driver(self):
        """The name is unchanged; only the previously-invalid network_driver is corrected."""
        platform = ensure_platform("cisco.ios.ios", "Cisco", adapter=self._adapter(False))

        self.assertEqual(platform.name, "cisco.ios.ios")
        self.assertEqual(platform.network_driver, "cisco_ios")
        self.assertEqual(platform.manufacturer, self.cisco)

    def test_raw_os_named_platform_keeps_its_name(self):
        """Mapper-expansion trap: fortios in LIBRENMS_LIB_MAPPER would rename and move devices."""
        platform = ensure_platform("fortios", "Fortinet", adapter=self._adapter(False))

        self.assertEqual(platform.name, "fortios")
        self.assertEqual(platform.network_driver, "fortinet")

    def test_existing_platform_driver_is_left_alone(self):
        """get_or_create defaults apply only on create, so no existing row is rewritten."""
        existing = ORMPlatform.objects.create(
            name="cisco.ios.ios", network_driver="cisco.ios.ios", manufacturer=self.cisco
        )

        platform = ensure_platform("cisco.ios.ios", "Cisco", adapter=self._adapter(False))

        self.assertEqual(platform.pk, existing.pk)
        self.assertEqual(platform.network_driver, "cisco.ios.ios")
        self.assertEqual(ORMPlatform.objects.count(), 1)

    def test_diffsync_attribute_is_still_the_platform_name(self):
        """Explicitly pin the legacy default so a refactor cannot silently flip it."""
        platform = ensure_platform("cisco.nxos.nxos", "Cisco", adapter=self._adapter(False))
        self.assertEqual(platform.name, "cisco.nxos.nxos")

    def test_no_adapter_defaults_to_legacy(self):
        """Callers that pass no adapter get the pre-existing behavior."""
        platform = ensure_platform("cisco.ios.ios", "Cisco")
        self.assertEqual(platform.name, "cisco.ios.ios")


class TestEnsurePlatformConsolidatedMode(EnsurePlatformTestCase):
    """Consolidated mode keys Platform identity on the network driver."""

    def test_creates_driver_named_platform(self):
        """A fresh install gets device-onboarding's naming."""
        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.name, "cisco_ios")
        self.assertEqual(platform.network_driver, "cisco_ios")

    def test_reuses_onboarding_platform(self):
        """The interop goal: share the row device-onboarding created."""
        onboarded = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios")

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.pk, onboarded.pk)
        self.assertEqual(ORMPlatform.objects.count(), 1)

    def test_adopts_legacy_fqcn_platform_without_modifying_it(self):
        """Enabling the flag must not fork a new row or rewrite the legacy one."""
        legacy = ORMPlatform.objects.create(
            name="cisco.ios.ios", network_driver="cisco.ios.ios", manufacturer=self.cisco
        )

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.pk, legacy.pk)
        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "cisco.ios.ios")
        self.assertEqual(legacy.network_driver, "cisco.ios.ios")
        self.assertEqual(ORMPlatform.objects.count(), 1)

    def test_adopts_dna_center_style_platform(self):
        """FQCN name with a correct driver is matched on the driver."""
        existing = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.pk, existing.pk)
        self.assertEqual(ORMPlatform.objects.count(), 1)

    def test_adopts_legacy_raw_os_platform(self):
        """A row named after the raw LibreNMS OS is adopted in place."""
        legacy = ORMPlatform.objects.create(name="fortios", network_driver="fortios", manufacturer=self.fortinet)

        platform = ensure_platform("fortinet", "Fortinet", adapter=self._adapter(True))

        self.assertEqual(platform.pk, legacy.pk)
        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "fortios")
        self.assertEqual(ORMPlatform.objects.count(), 1)

    def test_cisco_xe_does_not_steal_cisco_ios_fqcn(self):
        """The step-2 guard. Without it the outcome depends on device processing order."""
        legacy = ORMPlatform.objects.create(
            name="cisco.ios.ios", network_driver="cisco.ios.ios", manufacturer=self.cisco
        )

        platform = ensure_platform("cisco_xe", "Cisco", adapter=self._adapter(True))

        self.assertNotEqual(platform.pk, legacy.pk)
        self.assertEqual(platform.name, "cisco_xe")
        self.assertEqual(platform.network_driver, "cisco_xe")
        legacy.refresh_from_db()
        self.assertEqual(legacy.name, "cisco.ios.ios")

    def test_refuses_to_adopt_a_row_claimed_by_another_driver(self):
        """A legacy-named row whose driver belongs to someone else is left alone."""
        claimed = ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_nxos")

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertNotEqual(platform.pk, claimed.pk)
        self.assertEqual(platform.name, "cisco_ios")

    def test_duplicate_drivers_resolve_deterministically(self):
        """Regression test for MultipleObjectsReturned: duplicates are a legitimate state."""
        exact = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_ios")
        ORMPlatform.objects.create(name="cisco.ios.ios", network_driver="cisco_ios")
        ORMPlatform.objects.create(name="another-ios", network_driver="cisco_ios")

        for _ in range(3):
            platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))
            self.assertEqual(platform.pk, exact.pk)

    def test_prefers_matching_manufacturer(self):
        """Among equally-named candidates, the device's own Manufacturer wins."""
        ORMPlatform.objects.create(name="ios-generic", network_driver="cisco_ios")
        matching = ORMPlatform.objects.create(name="ios-cisco", network_driver="cisco_ios", manufacturer=self.cisco)

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.pk, matching.pk)

    def test_skips_conflicting_manufacturer(self):
        """A row belonging to a different Manufacturer is never reused."""
        conflicting = ORMPlatform.objects.create(
            name="ios-fortinet", network_driver="cisco_ios", manufacturer=self.fortinet
        )

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertNotEqual(platform.pk, conflicting.pk)
        self.assertEqual(platform.name, "cisco_ios")

    def test_backfills_blank_driver_on_exactly_named_row(self):
        """Self-heal an operator row named like the driver but missing it."""
        existing = ORMPlatform.objects.create(name="cisco_ios", network_driver="")

        platform = ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        self.assertEqual(platform.pk, existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.network_driver, "cisco_ios")

    def test_never_overwrites_a_disagreeing_driver(self):
        """A row named like the driver but carrying a different one is not rewritten."""
        existing = ORMPlatform.objects.create(name="cisco_ios", network_driver="cisco_nxos")

        ensure_platform("cisco_ios", "Cisco", adapter=self._adapter(True))

        existing.refresh_from_db()
        self.assertEqual(existing.network_driver, "cisco_nxos")

    def test_unknown_os_keeps_raw_name_and_blank_driver(self):
        """An intentionally unmapped OS is never given an invented driver."""
        platform = ensure_platform("opnsense", "Opnsense", adapter=self._adapter(True))

        self.assertEqual(platform.name, "opnsense")
        self.assertEqual(platform.network_driver, "")

    def test_adopts_existing_unmapped_os_platform(self):
        """An existing raw-OS row for an unmapped OS produces no new row."""
        existing = ORMPlatform.objects.create(name="opnsense", network_driver="")

        platform = ensure_platform("opnsense", "Opnsense", adapter=self._adapter(True))

        self.assertEqual(platform.pk, existing.pk)
        self.assertEqual(ORMPlatform.objects.count(), 1)
