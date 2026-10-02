"""Tests for the Cisco SD-WAN Nautobot (target) DiffSync models."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import (
    Controller,
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareVersion,
)
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VRF, IPAddress, IPAddressToInterface, Namespace

from nautobot_ssot.integrations.cisco_sdwan.diffsync.adapters.nautobot import CiscoSdwanNautobotAdapter
from nautobot_ssot.integrations.cisco_sdwan.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotIPAddressToInterface,
)


class CiscoSdwanModelTestCase(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Shared Nautobot object setup for the model tests."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Create the Nautobot objects shared by the tests."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        self.status_retired = Status.objects.get_or_create(name="Retired")[0]
        for model in [Controller, Device, Interface]:
            self.status_active.content_types.add(ContentType.objects.get_for_model(model))
            self.status_retired.content_types.add(ContentType.objects.get_for_model(model))
        self.status_active.content_types.add(ContentType.objects.get_for_model(SoftwareVersion))

        location_type = LocationType.objects.get_or_create(name="Site")[0]
        location_type.content_types.add(ContentType.objects.get_for_model(Device))
        location_type.content_types.add(ContentType.objects.get_for_model(Controller))
        self.location = Location.objects.create(name="Staging", location_type=location_type, status=self.status_active)

        manufacturer = Manufacturer.objects.get_or_create(name="Cisco")[0]
        self.device_type = DeviceType.objects.get_or_create(model="C8000V", manufacturer=manufacturer)[0]
        self.platform = Platform.objects.get_or_create(name="cisco_ios", manufacturer=manufacturer)[0]
        self.software_version = SoftwareVersion.objects.create(
            version="17.09.04", platform=self.platform, status=self.status_active
        )
        self.device_role = Role.objects.get_or_create(name="Router")[0]
        self.device_role.content_types.add(ContentType.objects.get_for_model(Device))

        controller = Controller.objects.create(name="SD-WAN Manager", status=self.status_active, location=self.location)
        self.managed_device_group = ControllerManagedDeviceGroup.objects.create(
            name="SD-WAN Managed Devices", controller=controller
        )

        self.device = Device.objects.create(
            name="sdwan-edge-01",
            status=self.status_active,
            role=self.device_role,
            device_type=self.device_type,
            platform=self.platform,
            location=self.location,
            controller_managed_device_group=self.managed_device_group,
        )
        self.primary_interface = Interface.objects.create(
            name="sdwan-system-intf",
            device=self.device,
            status=self.status_active,
            type="other",
        )
        self.interface = Interface.objects.create(
            name="GigabitEthernet1",
            device=self.device,
            status=self.status_active,
            type="other",
        )

        self.job = MagicMock()
        self.job.debug = False
        self.job.devices = None
        self.job.managed_device_group = self.managed_device_group
        self.job.device_platform = self.platform
        self.job.namespace = Namespace.objects.get_or_create(name="Global")[0]
        self.job.ignore_address_mask = True
        self.job.delete_replaced_ips = False
        self.adapter = CiscoSdwanNautobotAdapter(job=self.job, sync=None)

    def load_diffsync_object(self, modelname, unique_id):
        """Load the Nautobot adapter and return a single diffsync object from its store."""
        self.adapter.load()
        return self.adapter.get(modelname, unique_id)


class TestNautobotDevice(CiscoSdwanModelTestCase):
    """Test the NautobotDevice model."""

    def test_create(self):
        """Validate a Device is created and added to the managed device group."""
        ids = {"name": "sdwan-edge-02"}
        attrs = {
            "status__name": "Active",
            "role__name": "Router",
            "device_type__model": "C8000V",
            "platform__name": "cisco_ios",
            "location__name": "Staging",
            "serial": "BBBB2222CCCC",
        }
        result = NautobotDevice.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotDevice)
        device = Device.objects.get(name="sdwan-edge-02")
        self.assertEqual(device.serial, "BBBB2222CCCC")
        self.assertEqual(device.controller_managed_device_group, self.managed_device_group)

    def test_create_existing_device(self):
        """Validate creation is refused with an error when the Device already exists."""
        result = NautobotDevice.create(self.adapter, {"name": "sdwan-edge-01"}, {})
        self.assertIsNone(result)
        self.job.logger.error.assert_called_once()

    def test_update_keeps_location(self):
        """Validate the Device Location is never updated by the sync."""
        device = self.load_diffsync_object("device", "sdwan-edge-01")
        device.update({"location__name": "Somewhere Else"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.location, self.location)

    def test_update_software_version_platform_fallback(self):
        """Validate the SoftwareVersion platform falls back to the Job's device platform."""
        device = self.load_diffsync_object("device", "sdwan-edge-01")
        device.update({"software_version__version": "17.09.04"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.software_version, self.software_version)

    def test_update_platform_without_version_is_skipped(self):
        """Validate a platform-only software version update is dropped for Devices without a version."""
        device = self.load_diffsync_object("device", "sdwan-edge-01")
        device.update({"software_version__platform__name": "cisco_ios"})
        self.device.refresh_from_db()
        self.assertIsNone(self.device.software_version)

    def test_delete_sets_retired_status(self):
        """Validate deletion soft-deletes the Device by setting the retired status."""
        device = self.load_diffsync_object("device", "sdwan-edge-01")
        device.delete()
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, self.status_retired)
        self.assertTrue(Device.objects.filter(name="sdwan-edge-01").exists())


class TestNautobotIPAddressToInterface(CiscoSdwanModelTestCase):
    """Test the NautobotIPAddressToInterface model."""

    def _create_assignment(self, interface_name, host, mask_length, vrf_name=None):
        """Run NautobotIPAddressToInterface.create for the given interface and address."""
        ids = {
            "interface__device__name": "sdwan-edge-01",
            "interface__name": interface_name,
            "ip_address__host": host,
            "ip_address__mask_length": mask_length,
        }
        attrs = {"interface__vrf__name": vrf_name}
        return NautobotIPAddressToInterface.create(self.adapter, ids, attrs)

    def test_create(self):
        """Validate the IPAddress is created and assigned to the Interface."""
        result = self._create_assignment("GigabitEthernet1", "192.0.2.10", 24)
        self.assertIsInstance(result, NautobotIPAddressToInterface)
        assignment = IPAddressToInterface.objects.get(interface=self.interface)
        self.assertEqual(assignment.ip_address.host, "192.0.2.10")
        self.device.refresh_from_db()
        self.assertIsNone(self.device.primary_ip4)

    def test_create_sets_primary_ip(self):
        """Validate the Device primary IP is set for configured primary IP interfaces."""
        self._create_assignment("sdwan-system-intf", "10.255.1.1", 32)
        self.device.refresh_from_db()
        self.assertEqual(self.device.primary_ip4.host, "10.255.1.1")

    def test_create_with_vrf(self):
        """Validate the VRF is created and associated with the Interface and Device."""
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24, vrf_name="10")
        vrf = VRF.objects.get(name="10")
        self.interface.refresh_from_db()
        self.assertEqual(self.interface.vrf, vrf)
        self.assertIn(vrf, self.device.vrfs.all())

    def test_create_replaces_existing_assignment(self):
        """Validate a replaced IP is unassigned but not deleted by default."""
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24)
        self._create_assignment("GigabitEthernet1", "192.0.2.20", 24)
        assignments = IPAddressToInterface.objects.filter(interface=self.interface)
        self.assertEqual({a.ip_address.host for a in assignments}, {"192.0.2.20"})
        self.assertTrue(IPAddress.objects.filter(host="192.0.2.10").exists())

    def test_create_replaces_and_deletes_orphaned_ip(self):
        """Validate a replaced IP is deleted when delete_replaced_ips is enabled."""
        self.job.delete_replaced_ips = True
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24)
        self._create_assignment("GigabitEthernet1", "192.0.2.20", 24)
        self.assertFalse(IPAddress.objects.filter(host="192.0.2.10").exists())

    def test_create_with_unresolvable_ip(self):
        """Validate None is returned when the IPAddress cannot be resolved."""
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24)
        result = self._create_assignment("sdwan-system-intf", "192.0.2.10", 32)
        self.assertIsNone(result)

    def test_update_vrf(self):
        """Validate the Interface VRF is updated."""
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24, vrf_name="10")
        assignment = self.load_diffsync_object(
            "ip_address_to_interface", "sdwan-edge-01__GigabitEthernet1__192.0.2.10__24"
        )
        assignment.update({"interface__vrf__name": "20"})
        self.interface.refresh_from_db()
        self.assertEqual(self.interface.vrf.name, "20")

    def test_delete_cleans_up_vrf(self):
        """Validate deletion removes the VRF associations and unused VRFs."""
        self._create_assignment("GigabitEthernet1", "192.0.2.10", 24, vrf_name="10")
        assignment = self.load_diffsync_object(
            "ip_address_to_interface", "sdwan-edge-01__GigabitEthernet1__192.0.2.10__24"
        )
        assignment.delete()
        self.interface.refresh_from_db()
        self.assertIsNone(self.interface.vrf)
        self.assertNotIn("10", self.device.vrfs.values_list("name", flat=True))
        self.assertFalse(VRF.objects.filter(name="10").exists())
