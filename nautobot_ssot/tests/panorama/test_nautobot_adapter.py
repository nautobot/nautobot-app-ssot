"""Test Nautobot adapter."""

from unittest.mock import MagicMock

from nautobot.apps.testing import TransactionTestCase
from nautobot.dcim.models import (
    Controller,
    Device,
    DeviceType,
    Interface,
    InterfaceVDCAssignment,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareVersion,
    VirtualDeviceContext,
)
from nautobot.dcim.models import (
    ControllerManagedDeviceGroup as NBControllerManagedDeviceGroup,
)
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix

from nautobot_ssot.integrations.panorama.diffsync.adapters.nautobot import PanoSSoTNautobotAdapter
from nautobot_ssot.integrations.panorama.models import (
    LogicalGroup,
    LogicalGroupToDevice,
    LogicalGroupToVirtualDeviceContext,
)


class TestNautobotAdapterLoads(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test Nautobot adapter load methods."""

    databases = ("default", "job_logs")

    def setUp(self):
        # pylint: disable=too-many-statements, duplicate-code, R0801
        """Initialize test case."""
        super().setUp()

        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.device_role, _ = Role.objects.get_or_create(name="Firewall")
        self.manufacturer, _ = Manufacturer.objects.get_or_create(name="Palo Alto")
        self.platform, _ = Platform.objects.get_or_create(name="paloalto_panos")
        self.device_type, _ = DeviceType.objects.get_or_create(
            model="PA-3220",
            part_number="PAN-PA-3220",
            manufacturer=self.manufacturer,
        )
        self.device_type_2, _ = DeviceType.objects.get_or_create(
            model="PA-5220",
            part_number="PAN-PA-5220",
            manufacturer=self.manufacturer,
        )
        self.location_type, _ = LocationType.objects.get_or_create(name="Site")
        self.location, _ = Location.objects.get_or_create(
            name="Test Site",
            location_type=self.location_type,
            status=self.status_active,
        )
        self.namespace, _ = Namespace.objects.get_or_create(name="Global")
        self.prefix, _ = Prefix.objects.get_or_create(
            prefix="10.0.0.0/24",
            namespace=self.namespace,
            status=self.status_active,
        )
        self.device, _ = Device.objects.get_or_create(
            name="fw-01",
            serial="serial001",
            device_type=self.device_type,
            platform=self.platform,
            role=self.device_role,
            status=self.status_active,
            location=self.location,
        )
        self.device_2, _ = Device.objects.get_or_create(
            name="fw-02",
            serial="serial002",
            device_type=self.device_type_2,
            platform=self.platform,
            role=self.device_role,
            status=self.status_active,
            location=self.location,
        )
        self.interface, _ = Interface.objects.get_or_create(
            name="ethernet1/1",
            device=self.device,
            type="other",
            status=self.status_active,
        )
        self.interface_2, _ = Interface.objects.get_or_create(
            name="ethernet1/2",
            device=self.device,
            type="other",
            status=self.status_active,
        )
        self.ip_address, _ = IPAddress.objects.get_or_create(
            address="10.0.0.1/24",
            namespace=self.namespace,
            status=self.status_active,
        )
        self.ip_address_2, _ = IPAddress.objects.get_or_create(
            address="10.0.0.2/24",
            namespace=self.namespace,
            status=self.status_active,
        )
        self.ip_address.interfaces.add(self.interface)
        self.ip_address_2.interfaces.add(self.interface_2)

        self.device.primary_ip4 = self.ip_address
        self.device.save()
        self.device_2.primary_ip4 = self.ip_address_2
        self.device_2.save()

        self.controller, _ = Controller.objects.get_or_create(
            name="panorama-01",
            location=self.location,
            status=self.status_active,
        )
        self.controller_managed_device_group, _ = NBControllerManagedDeviceGroup.objects.get_or_create(
            name="panorama-01 - Panorama Devices",
            controller=self.controller,
        )
        self.controller_managed_device_group.devices.add(self.device)
        self.controller_managed_device_group.devices.add(self.device_2)

        self.software_version, _ = SoftwareVersion.objects.get_or_create(
            platform=self.platform,
            version="10.1.0",
            status=self.status_active,
        )
        self.device.software_version = self.software_version
        self.device.save()
        self.device_2.software_version = self.software_version
        self.device_2.save()

        self.vsys_1, _ = VirtualDeviceContext.objects.get_or_create(
            name="vsys1",
            device=self.device,
            identifier=1,
            status=self.status_active,
        )
        self.vsys_2, _ = VirtualDeviceContext.objects.get_or_create(
            name="vsys2",
            device=self.device,
            identifier=2,
            status=self.status_active,
        )

        self.logical_group, _ = LogicalGroup.objects.get_or_create(
            name="device-group-1",
        )
        self.logical_group_to_device, _ = LogicalGroupToDevice.objects.get_or_create(
            group=self.logical_group,
            device=self.device,
        )
        self.logical_group_to_vsys, _ = LogicalGroupToVirtualDeviceContext.objects.get_or_create(
            group=self.logical_group,
            virtual_device_context=self.vsys_1,
        )
        self.vsys_association, _ = InterfaceVDCAssignment.objects.get_or_create(
            virtual_device_context=self.vsys_1,
            interface=self.interface,
        )

        self.panorama_controller = MagicMock()
        self.panorama_controller.name = "panorama-01"
        self.panorama_controller.logical_groups.all.return_value = []

        self.job = MagicMock()
        self.job.loaded_panorama_devices = {"serial001", "serial002"}
        self.job.debug = False
        self.job.panorama_controller = self.panorama_controller
        self.job.logger = MagicMock()

    def _create_adapter(self):
        """Create a Nautobot adapter."""
        adapter = PanoSSoTNautobotAdapter(job=self.job, sync=MagicMock())
        return adapter

    def test_load_device_types(self):
        """Test loading device types from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_device_types()

        identifier = f"{self.device_type.model}__{self.manufacturer.name}"
        stored = adapter.store.get(model="device_type", identifier=identifier)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.model, self.device_type.model)

    def test_load_firewalls(self):
        """Test loading firewalls from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_firewalls()

        stored = adapter.store.get(model="firewall", identifier=self.device.serial)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.serial, self.device.serial)

    def test_load_firewall_interfaces(self):
        """Test loading firewall interfaces from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_firewall_interfaces()

        identifier = f"{self.device.serial}__{self.interface.name}"
        stored = adapter.store.get(model="firewall_interface", identifier=identifier)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.name, self.interface.name)

    def test_load_ip_address_to_interface_objects(self):
        """Test loading IP address to interface objects from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_ip_address_to_interface_objects()

        identifier = (
            f"{self.device.serial}__{self.interface.name}__{self.ip_address.host}__{self.ip_address.mask_length}"
        )
        stored = adapter.store.get(model="ip_address_to_interface", identifier=identifier)
        self.assertIsNotNone(stored)

    def test_load_devices_to_controller_managed_device_groups(self):
        """Test loading device to controller managed device group from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_devices_to_controller_managed_device_groups()

        identifier = f"{self.device.serial}__{self.controller_managed_device_group.name}"
        stored = adapter.store.get(model="devicetocontrollermanageddevicegroup", identifier=identifier)
        self.assertIsNotNone(stored)

    def test_load_software_versions_to_devices(self):
        """Test loading software versions to devices from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_software_versions_to_devices()

        identifier = f"{self.device.serial}__{self.platform.name}__{self.software_version.version}"
        stored = adapter.store.get(model="softwareversiontodevice", identifier=identifier)
        self.assertIsNotNone(stored)

    def test_load_virtual_device_contexts(self):
        """Test loading virtual system objects from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_virtual_device_contexts()

        identifier = f"{self.vsys_1.device.serial}__{self.vsys_1.name}"
        stored = adapter.store.get(model="vdc", identifier=identifier)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.name, self.vsys_1.name)

    def test_load_logical_groups_to_devices(self):
        """Test loading logical groups to devices from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_logical_groups_to_devices()

        identifier = f"{self.logical_group.name}__{self.device.serial}"
        stored = adapter.store.get(model="logicalgrouptodevice", identifier=identifier)
        self.assertIsNotNone(stored)

    def test_load_virtual_device_context_associations(self):
        """Test loading virtual system associations from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_virtual_device_context_associations()

        identifier = (
            f"{self.vsys_1.device.serial}__{self.vsys_1.name}__{self.interface.device.serial}__{self.interface.name}"
        )
        stored = adapter.store.get(model="virtualdevicecontextassociation", identifier=identifier)
        self.assertIsNotNone(stored)

    def test_load_logical_groups_to_virtual_device_contexts(self):
        """Test loading logical groups to virtual systems from Nautobot."""
        adapter = self._create_adapter()
        adapter.load_logical_groups_to_virtual_device_contexts()

        identifier = f"{self.logical_group.name}__{self.vsys_1.device.serial}__{self.vsys_1.name}"
        stored = adapter.store.get(model="logicalgrouptovirtualdevicecontext", identifier=identifier)
        self.assertIsNotNone(stored)
