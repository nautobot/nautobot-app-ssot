"""Unit tests for LibreNMS DiffSync models."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.test import TestCase
from nautobot.dcim.models import Device as NautobotDevice
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status

from nautobot_ssot.integrations.librenms.diffsync.models.librenms import LibrenmsDevice, LibrenmsLocation
from nautobot_ssot.tests.librenms.fixtures import (
    ADD_LIBRENMS_DEVICE_FAILURE,
    ADD_LIBRENMS_DEVICE_PING_FALLBACK,
    ADD_LIBRENMS_DEVICE_SUCCESS,
)


class TestAdapter(Adapter):
    """Test adapter class that inherits from diffsync.Adapter."""

    def __init__(self):
        super().__init__()
        self.job = MagicMock()
        self.lnms_api = MagicMock()


class TestLibrenmsLocation(TestCase):
    """Test cases for LibrenmsLocation model."""

    def setUp(self):
        """Set up test case."""
        mock_adapter = MagicMock(spec=Adapter)
        mock_adapter.job = MagicMock()
        mock_adapter.lnms_api = MagicMock()
        self.adapter = mock_adapter

        Status.objects.get_or_create(
            name="Active", defaults={"color": "4caf50", "description": "Unit Testing Active Status"}
        )

    def test_create_location_success(self):
        """Test creating a location with valid data."""
        ids = {"name": "City Hall"}
        attrs = {
            "status": "Active",
            "latitude": 41.874677,
            "longitude": -87.626728,
            "location_type": "Site",
            "system_of_record": "LibreNMS",
        }

        LibrenmsLocation.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_location.assert_called_once_with(
            {
                "location": "City Hall",
                "lat": 41.874677,
                "lng": -87.626728,
            }
        )

    def test_create_location_no_coordinates(self):
        """Test creating a location without coordinates."""
        ids = {"name": "City Hall"}
        attrs = {
            "status": "Active",
            "latitude": None,
            "longitude": None,
            "location_type": "Site",
            "system_of_record": "LibreNMS",
        }

        LibrenmsLocation.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_location.assert_not_called()
        self.adapter.job.logger.warning.assert_called_once()

    def test_create_location_inactive(self):
        """Test creating an inactive location."""
        ids = {"name": "City Hall"}
        attrs = {
            "status": "Offline",
            "latitude": 41.874677,
            "longitude": -87.626728,
            "location_type": "Site",
            "system_of_record": "LibreNMS",
        }

        LibrenmsLocation.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_location.assert_not_called()


class TestLibrenmsDevice(TestCase):
    """Test cases for LibrenmsDevice model."""

    def setUp(self):
        """Set up test case."""
        super().setUp()
        self.adapter = TestAdapter()

        self.responses = {
            "success": ADD_LIBRENMS_DEVICE_SUCCESS,
            "failure": ADD_LIBRENMS_DEVICE_FAILURE,
            "ping_fallback": ADD_LIBRENMS_DEVICE_PING_FALLBACK,
        }

        self.status = Status.objects.get_or_create(
            name="Active", defaults={"color": "4caf50", "description": "Unit Testing Active Status"}
        )[0]

        device_type = self.create_device_dependencies()

        location_type = LocationType.objects.get_or_create(name="Site")[0]
        self.location = Location.objects.get_or_create(
            name="Test Location",
            location_type=location_type,
            status=self.status,
            defaults={"description": "Test Location for Unit Tests"},
        )[0]

        self.device_role = Role.objects.get_or_create(name="Test Role", defaults={"color": "ff0000"})[0]

        self.device = NautobotDevice.objects.get_or_create(
            name="test-device",
            defaults={
                "status": self.status,
                "device_type": device_type,
                "location": self.location,
                "role": self.device_role,
            },
        )[0]

    def create_device_dependencies(self):
        """Create the minimum required objects for a Device."""

        manufacturer = Manufacturer.objects.get_or_create(name="Generic")[0]
        device_type = DeviceType.objects.get_or_create(
            manufacturer=manufacturer,
            model="Test Device Type",
            defaults={
                "manufacturer": manufacturer,
            },
        )[0]
        return device_type

    @patch("nautobot.dcim.models.Device.objects.get")
    def test_create_device_success(self, mock_device_get):  # pylint: disable=W0613
        """Test creating a device with valid data."""
        device_name = "test-device"
        ids = {"name": device_name}
        attrs = {
            "ip_address": "192.168.1.1",
            "location": "City Hall",
            "device_type": "Generic Device",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
            "status": "Active",
        }

        self.adapter.job.source_adapter.dict.return_value = {"device": {device_name: attrs}}

        LibrenmsDevice.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_device.assert_called_once_with(
            {
                "hostname": "192.168.1.1",
                "display": device_name,
                "location": "City Hall",
                "force_add": True,
                "ping_fallback": True,
            }
        )

    def test_create_device_default(self):
        """Test creating a device with default settings."""
        device_name = "LIBRENMSDEV"
        ids = {"name": device_name}
        attrs = {
            "ip_address": "192.168.1.2",
            "location": "City Hall",
            "device_type": "Generic Device",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
            "status": "Active",
        }

        device_type = self.create_device_dependencies()
        NautobotDevice.objects.get_or_create(
            name=device_name,
            defaults={
                "status": self.status,
                "device_type": device_type,
                "location": self.location,
                "role": self.device_role,
            },
        )

        self.adapter.job.source_adapter.dict.return_value = {"device": {device_name: attrs}}

        self.adapter.lnms_api.create_librenms_device.return_value = self.responses["success"]

        device = LibrenmsDevice.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_device.assert_called_once_with(
            {
                "hostname": "192.168.1.2",
                "display": device_name,
                "location": "City Hall",
                "force_add": True,
                "ping_fallback": True,
            }
        )

        self.assertEqual(device.name, self.responses["success"]["devices"][0]["display"])

    def test_create_device_with_ping_fallback(self):
        """Test creating a device with ping_fallback enabled."""
        ids = {"name": "test-device"}
        attrs = {
            "ip_address": "192.168.1.1",
            "location": "City Hall",
            "device_type": "Generic Device",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
            "platform": "linux",
            "role": "Server",
            "status": "Active",
            "os_version": "1.0",
            "device_id": "123",
            "serial_no": "ABC123",
        }

        mock_adapter = MagicMock(spec=Adapter)
        mock_adapter.job = MagicMock()
        mock_adapter.lnms_api = MagicMock()
        mock_adapter.dict.return_value = {"device": {"test-device": attrs}}

        LibrenmsDevice.create(mock_adapter, ids, attrs)

    def test_create_device_failure_no_ping(self):
        """Test creating a device with ping failure."""
        device_name = "test-device-no-ping"
        ids = {"name": device_name}
        attrs = {
            "ip_address": "192.168.1.3",
            "location": "City Hall",
            "device_type": "Generic Device",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
            "status": "Active",
        }

        self.adapter.job.source_adapter.dict.return_value = {"device": {device_name: attrs}}

        self.adapter.lnms_api.create_librenms_device.side_effect = Exception(
            self.responses["failure"]["no_ping"]["message"]
        )

        with self.assertRaises(Exception) as context:
            LibrenmsDevice.create(self.adapter, ids, attrs)

        self.assertEqual(str(context.exception), self.responses["failure"]["no_ping"]["message"])

    def test_create_device_failure_no_snmp(self):
        """Test creating a device with SNMP failure."""
        device_name = "test-device-no-snmp"
        ids = {"name": device_name}
        attrs = {
            "ip_address": "192.168.1.4",
            "location": "City Hall",
            "device_type": "Generic Device",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
            "status": "Active",
        }

        self.adapter.job.source_adapter.dict.return_value = {"device": {device_name: attrs}}

        self.adapter.lnms_api.create_librenms_device.side_effect = Exception(
            self.responses["failure"]["no_snmp"]["message"]
        )

        with self.assertRaises(Exception) as context:
            LibrenmsDevice.create(self.adapter, ids, attrs)

        self.assertEqual(str(context.exception), self.responses["failure"]["no_snmp"]["message"])

    def test_create_device_no_ip(self):
        """Test creating a device without an IP address."""
        ids = {"name": "test-device"}
        attrs = {
            "status": "Active",
            "location": "City Hall",
            "device_type": "Linux",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
        }
        self.adapter.job.source_adapter.dict.return_value = {"device": {"test-device": {"ip_address": None}}}

        LibrenmsDevice.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_device.assert_not_called()
        self.adapter.job.logger.debug.assert_called_once()

    def test_create_device_inactive(self):
        """Test creating an inactive device."""
        ids = {"name": "test-device"}
        attrs = {
            "status": "Offline",
            "location": "City Hall",
            "device_type": "Linux",
            "manufacturer": "Generic",
            "system_of_record": "LibreNMS",
        }

        LibrenmsDevice.create(self.adapter, ids, attrs)

        self.adapter.lnms_api.create_librenms_device.assert_not_called()
