"""Unit tests for Arista CV Nautobot DiffSync model behavior."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device as OrmDevice
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer, Platform, SoftwareVersion
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.aristacv.constants import ARISTA_PLATFORM
from nautobot_ssot.integrations.aristacv.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotNamespace,
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
class TestNautobotNamespaceDelete(TransactionTestCase):
    """Test NautobotNamespace.delete() conditional on delete_namespaces_on_sync."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up adapter with job and app_config."""
        super().setUp()
        self.adapter = MagicMock()
        self.adapter.objects_to_delete = defaultdict(list)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.app_config = get_config()._replace(delete_namespaces_on_sync=False)

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
class TestNautobotPrefixDelete(TransactionTestCase):
    """Test NautobotPrefix.delete() conditional on delete_prefixes_on_sync."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up adapter with job and app_config."""
        super().setUp()
        self.adapter = MagicMock()
        self.adapter.objects_to_delete = defaultdict(list)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.app_config = get_config()._replace(delete_prefixes_on_sync=False)
        self.ns = OrmNamespace.objects.create(name="PrefixTestNS")
        self.status_active = Status.objects.get(name="Active")
        self.prefix = OrmPrefix.objects.create(prefix="10.99.0.0/24", namespace=self.ns, status=self.status_active)

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
            "aristacv_from_cloudvision_default_site": "TestSite",
            "aristacv_from_cloudvision_default_device_role": "Edge Router",
        },
    },
)
class TestNautobotDeviceVersion(TransactionTestCase):
    """Test that NautobotDevice.create() and update() correctly assign software_version."""

    databases = ("default", "job_logs")

    ATTRS = {
        "device_model": "DCS-7150S-24",
        "serial": "ABC123",
        "status": "Active",
        "version": "4.28.1F",
    }
    IDS = {"name": "switch-01"}

    def setUp(self):
        """Set up adapter with job and app_config plus baseline ORM objects."""
        super().setUp()
        # spec=Adapter so pydantic's is_instance_of check on DiffSyncModel.adapter passes.
        self.adapter = MagicMock(spec=Adapter)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.app_config = get_config()
        self.status_active = Status.objects.get(name="Active")
        arista_manu = Manufacturer.objects.get_or_create(name="Arista")[0]
        self.arista_platform = Platform.objects.get_or_create(name=ARISTA_PLATFORM, manufacturer=arista_manu)[0]
        self.device_type = DeviceType.objects.get_or_create(model="DCS-7150S-24", manufacturer=arista_manu)[0]
        device_ct = ContentType.objects.get_for_model(OrmDevice)
        self.role = Role.objects.get_or_create(name="Edge Router", color="ff0000")[0]
        self.role.content_types.add(device_ct)
        location_type = LocationType.objects.get_or_create(name="Site")[0]
        location_type.content_types.add(device_ct)
        self.location = Location.objects.create(
            name="UpdateSite",
            location_type=location_type,
            status=self.status_active,
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
