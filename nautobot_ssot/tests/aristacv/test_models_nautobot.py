"""Unit tests for Arista CV Nautobot DiffSync models."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import DeviceType, Interface, Location, LocationType, Manufacturer, Platform, SoftwareVersion
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress as OrmIPAddress
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.aristacv.constants import ARISTA_PLATFORM
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotIPAddress,
    NautobotNamespace,
    NautobotPort,
    NautobotPrefix,
)
from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotNamespaceDelete(TestCase):
    """Test NautobotNamespace.delete() conditional on delete_namespaces_on_sync."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Set up adapter with job and app_config."""
        super().setUpTestData()
        cls.adapter = MagicMock()
        cls.adapter.objects_to_delete = defaultdict(list)
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = False
        cls.adapter.job.app_config = get_config()._replace(delete_namespaces_on_sync=False)

    def test_namespace_delete_when_delete_on_sync_false(self):
        """When delete_namespaces_on_sync is False, delete() does not append to objects_to_delete."""
        ns = OrmNamespace.objects.create(name="NoDeleteNS")
        model = NautobotNamespace(name="NoDeleteNS", uuid=ns.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["namespaces"]), 0)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmNamespace.objects.get")
    def test_namespace_delete_when_delete_on_sync_true(self, mock_ns_get):
        """When delete_namespaces_on_sync is True, delete() appends namespace to objects_to_delete."""
        ns = OrmNamespace.objects.create(name="DeleteNS")
        mock_ns_get.return_value = ns
        self.adapter.job.app_config = get_config()._replace(delete_namespaces_on_sync=True)
        model = NautobotNamespace(name="DeleteNS", uuid=ns.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["namespaces"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["namespaces"][0].id, ns.id)


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotPrefixDelete(TestCase):
    """Test NautobotPrefix.delete() conditional on delete_prefixes_on_sync."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Set up adapter with job and app_config."""
        super().setUpTestData()
        populate_status_choices()
        cls.adapter = MagicMock()
        cls.adapter.objects_to_delete = defaultdict(list)
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = False
        cls.adapter.job.app_config = get_config()._replace(delete_prefixes_on_sync=False)
        cls.ns = OrmNamespace.objects.create(name="PrefixTestNS")
        cls.status_active = Status.objects.get(name="Active")
        cls.prefix = OrmPrefix.objects.create(prefix="10.99.0.0/24", namespace=cls.ns, status=cls.status_active)

    def test_prefix_delete_when_delete_on_sync_false(self):
        """When delete_prefixes_on_sync is False, delete() does not append to objects_to_delete."""
        model = NautobotPrefix(prefix="10.99.0.0/24", namespace=self.ns.name, uuid=self.prefix.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 0)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmPrefix.objects.get")
    def test_prefix_delete_when_delete_on_sync_true(self, mock_pf_get):
        """When delete_prefixes_on_sync is True, delete() appends prefix to objects_to_delete."""
        mock_pf_get.return_value = self.prefix
        self.adapter.job.app_config = get_config()._replace(delete_prefixes_on_sync=True)
        model = NautobotPrefix(prefix="10.99.0.0/24", namespace=self.ns.name, uuid=self.prefix.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["prefixes"][0].id, self.prefix.id)


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotIPAddressDelete(TestCase):
    """Test NautobotIPAddress.delete() conditional on delete_ipaddresses_on_sync."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Set up adapter with job and app_config."""
        super().setUpTestData()
        populate_status_choices()
        cls.adapter = MagicMock()
        cls.adapter.objects_to_delete = defaultdict(list)
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = False
        cls.adapter.job.app_config = get_config()._replace(delete_ipaddresses_on_sync=False)
        cls.ns = OrmNamespace.objects.create(name="IPTestNS")
        cls.status_active = Status.objects.get(name="Active")
        cls.prefix = OrmPrefix.objects.create(prefix="10.98.0.0/24", namespace=cls.ns, status=cls.status_active)
        cls.ipaddr = OrmIPAddress.objects.create(address="10.98.0.1/24", namespace=cls.ns, status=cls.status_active)

    def test_ipaddress_delete_when_delete_on_sync_false(self):
        """When delete_ipaddresses_on_sync is False, delete() does not append to objects_to_delete."""
        model = NautobotIPAddress(
            address="10.98.0.1/24", prefix="10.98.0.0/24", namespace=self.ns.name, uuid=self.ipaddr.id
        )
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["ipaddresses"]), 0)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmIPAddress.objects.get")
    def test_ipaddress_delete_when_delete_on_sync_true(self, mock_ip_get):
        """When delete_ipaddresses_on_sync is True, delete() appends IP address to objects_to_delete."""
        mock_ip_get.return_value = self.ipaddr
        self.adapter.job.app_config = get_config()._replace(delete_ipaddresses_on_sync=True)
        model = NautobotIPAddress(
            address="10.98.0.1/24", prefix="10.98.0.0/24", namespace=self.ns.name, uuid=self.ipaddr.id
        )
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["ipaddresses"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["ipaddresses"][0].id, self.ipaddr.id)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmIPAddress.objects.get")
    def test_ipaddress_delete_logs_warning_when_debug(self, mock_ip_get):
        """When delete_ipaddresses_on_sync and debug are True, delete() logs a warning."""
        mock_ip_get.return_value = self.ipaddr
        self.adapter.job.debug = True
        self.adapter.job.app_config = get_config()._replace(delete_ipaddresses_on_sync=True)
        model = NautobotIPAddress(
            address="10.98.0.1/24", prefix="10.98.0.0/24", namespace=self.ns.name, uuid=self.ipaddr.id
        )
        model.adapter = self.adapter
        model.delete()
        self.adapter.job.logger.warning.assert_called_once_with(
            "IPAddress 10.98.0.1/24 will be deleted per app settings."
        )
        self.assertEqual(len(self.adapter.objects_to_delete["ipaddresses"]), 1)


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
            "aristacv_from_cloudvision_default_site": "TestSite",
            "aristacv_from_cloudvision_default_device_role": "Edge Router",
        },
    },
)
class TestNautobotDeviceVersion(TestCase):
    """Test that NautobotDevice.create() and update() correctly assign software_version."""

    databases = ("default", "job_logs")

    ATTRS = {
        "device_model": "DCS-7150S-24",
        "serial": "ABC123",
        "status": "Active",
        "version": "4.28.1F",
    }
    IDS = {"name": "switch-01"}

    @classmethod
    def setUpTestData(cls):
        """Set up adapter with job and app_config plus baseline ORM objects."""
        super().setUpTestData()
        populate_status_choices()
        # spec=Adapter so pydantic's is_instance_of check on DiffSyncModel.adapter passes.
        cls.adapter = MagicMock(spec=Adapter)
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = False
        cls.adapter.job.app_config = get_config()
        cls.status_active = Status.objects.get(name="Active")
        arista_manu = Manufacturer.objects.get_or_create(name="Arista")[0]
        cls.arista_platform = Platform.objects.get_or_create(name=ARISTA_PLATFORM, manufacturer=arista_manu)[0]
        cls.device_type = DeviceType.objects.get_or_create(model="DCS-7150S-24", manufacturer=arista_manu)[0]
        device_ct = ContentType.objects.get_for_model(OrmDevice)
        cls.role = Role.objects.get_or_create(name="Edge Router", color="ff0000")[0]
        cls.role.content_types.add(device_ct)
        location_type = LocationType.objects.get_or_create(name="Site")[0]
        location_type.content_types.add(device_ct)
        cls.location = Location.objects.create(
            name="UpdateSite",
            location_type=location_type,
            status=cls.status_active,
        )

    def test_create_assigns_software_version(self):
        """Regression for #1173: create() must assign software_version on the first sync."""
        NautobotDevice.create(adapter=self.adapter, ids=self.IDS, attrs=self.ATTRS)
        device = OrmDevice.objects.get(name="switch-01")
        self.assertIsNotNone(device.software_version)
        self.assertEqual(device.software_version.version, "4.28.1F")
        self.assertEqual(device.software_version.platform, self.arista_platform)
        self.assertEqual(device.software_version.status, self.status_active)

    def test_create_without_version_leaves_software_version_unset(self):
        """When attrs has no version, create() leaves software_version unset."""
        attrs = {**self.ATTRS, "version": None}
        NautobotDevice.create(adapter=self.adapter, ids=self.IDS, attrs=attrs)
        device = OrmDevice.objects.get(name="switch-01")
        self.assertIsNone(device.software_version)

    def _build_device(self, software_version=None):
        """Create a real OrmDevice for use in update() tests."""
        return OrmDevice.objects.create(
            name="switch-02",
            status=self.status_active,
            device_type=self.device_type,
            role=self.role,
            platform=self.arista_platform,
            location=self.location,
            software_version=software_version,
        )

    def test_update_assigns_software_version(self):
        """update() with a new version assigns it via the helper."""
        device = self._build_device()
        model = NautobotDevice(
            name=device.name,
            device_model=self.device_type.model,
            serial="",
            status="Active",
            version=None,
            uuid=device.id,
        )
        model.adapter = self.adapter
        model.update({"version": "4.28.1F"})
        device.refresh_from_db()
        self.assertIsNotNone(device.software_version)
        self.assertEqual(device.software_version.version, "4.28.1F")
        self.assertEqual(device.software_version.status, self.status_active)

    def test_update_clears_software_version_when_version_set_none(self):
        """update() with version=None clears an existing software_version."""
        existing_sv = SoftwareVersion.objects.create(
            version="4.28.1F",
            platform=self.arista_platform,
            status=self.status_active,
        )
        device = self._build_device(software_version=existing_sv)
        model = NautobotDevice(
            name=device.name,
            device_model=self.device_type.model,
            serial="",
            status="Active",
            version="4.28.1F",
            uuid=device.id,
        )
        model.adapter = self.adapter
        model.update({"version": None})
        device.refresh_from_db()
        self.assertIsNone(device.software_version)


class TestNautobotPortCreate(TestCase):
    """Test NautobotPort.create() handles breakout interface names and lag references."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Create the minimal Nautobot scaffolding (status/site/devicetype/role/device)."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active, _ = Status.objects.get_or_create(name="Active")
        arista_manu, _ = Manufacturer.objects.get_or_create(name="Arista")

        loc_type, _ = LocationType.objects.get_or_create(name="Site")
        cls.status_active.content_types.add(ContentType.objects.get_for_model(Location))
        cls.site, _ = Location.objects.get_or_create(name="HQ", status=cls.status_active, location_type=loc_type)

        cls.device_type, _ = DeviceType.objects.get_or_create(model="DCS-7280CR2-60", manufacturer=arista_manu)
        role, _ = Role.objects.get_or_create(name="Switch")

        cls.device = OrmDevice.objects.create(
            name="ams01-switch-01",
            device_type=cls.device_type,
            status=cls.status_active,
            role=role,
            location=cls.site,
        )

        cls.warnings = []
        mock_job = MagicMock()
        mock_job.debug = False
        mock_job.logger.warning = lambda msg: cls.warnings.append(str(msg))
        cls.adapter = NautobotAdapter(job=mock_job)

    def _attrs(self, **overrides):
        attrs = {
            "description": "",
            "mac_addr": "fc:bd:67:00:00:01",
            "enabled": True,
            "mode": "access",
            "mtu": 9214,
            "port_type": "other",
            "status": "Active",
            "lag": None,
        }
        attrs.update(overrides)
        return attrs

    def test_create_breakout_interface_with_slash_in_name(self):
        """Regression: NautobotPort.create() must persist breakout interfaces (e.g. Ethernet53/1)."""
        ids = {"name": "Ethernet53/1", "device": self.device.name}
        NautobotPort.create(adapter=self.adapter, ids=ids, attrs=self._attrs())
        self.assertEqual(self.warnings, [], f"Unexpected warnings: {self.warnings}")
        self.assertTrue(
            Interface.objects.filter(device=self.device, name="Ethernet53/1").exists(),
            "Breakout interface Ethernet53/1 was not created on the device.",
        )

    def test_create_lag_member_when_parent_already_exists(self):
        """When the lag parent already exists, create() assigns the lag FK on the new interface."""
        parent = Interface.objects.create(
            device=self.device,
            name="Port-Channel1000",
            type="lag",
            status=self.status_active,
        )
        ids = {"name": "Ethernet53/1", "device": self.device.name}
        NautobotPort.create(adapter=self.adapter, ids=ids, attrs=self._attrs(lag="Port-Channel1000"))
        self.assertEqual(self.warnings, [], f"Unexpected warnings: {self.warnings}")
        intf = Interface.objects.get(device=self.device, name="Ethernet53/1")
        self.assertEqual(intf.lag_id, parent.id)


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotDeviceUpdate(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test NautobotDevice.update() persists supported attribute changes."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Build a Device with Active status and a configured adapter."""
        super().setUpTestData()
        populate_status_choices()
        cls.adapter = MagicMock()
        cls.adapter.job = MagicMock()
        cls.adapter.job.app_config = get_config()

        device_ct = ContentType.objects.get_for_model(OrmDevice)
        location_ct = ContentType.objects.get_for_model(Location)

        cls.status_active = Status.objects.get(name="Active")
        cls.status_offline, _ = Status.objects.get_or_create(name="Offline")
        for status in (cls.status_active, cls.status_offline):
            status.content_types.add(device_ct)
            status.content_types.add(location_ct)

        cls.role, _ = Role.objects.get_or_create(name="aristacv-test-switch")
        cls.role.content_types.add(device_ct)
        cls.manufacturer, _ = Manufacturer.objects.get_or_create(name="Arista")
        cls.device_type, _ = DeviceType.objects.get_or_create(
            model="aristacv-test-dt",
            manufacturer=cls.manufacturer,
        )
        cls.location_type, _ = LocationType.objects.get_or_create(name="Site")
        cls.location_type.content_types.add(device_ct)
        cls.location = Location.objects.create(
            name="DeviceUpdateSite",
            location_type=cls.location_type,
            status=cls.status_active,
        )
        cls.device = OrmDevice(
            name="sw-update-test",
            status=cls.status_active,
            role=cls.role,
            device_type=cls.device_type,
            location=cls.location,
        )
        cls.device.validated_save()
        cls.platform, _ = Platform.objects.get_or_create(name="arista.eos.eos")

    def test_update_persists_status_change(self):
        """update() with a status attribute writes the new status to the database."""
        model = NautobotDevice(
            name=self.device.name,
            device_model=self.device_type.model,
            serial="",
            status="Active",
            uuid=self.device.pk,
        )
        model.adapter = self.adapter

        model.update(attrs={"status": "Offline"})

        self.device.refresh_from_db()
        self.assertEqual(self.device.status.name, "Offline")
