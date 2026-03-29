"""Tests for Forward Networks integration."""

from unittest.mock import Mock, patch

from django.test import TestCase
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Status
from nautobot.ipam.models import Namespace

from nautobot_ssot.integrations.forward_networks.diffsync.adapters import ForwardNetworksAdapter, NautobotAdapter
from nautobot_ssot.tests.forward_networks.mocks import MockForwardNetworksClient


class TestForwardNetworksAdapter(TestCase):
    """Test Forward Networks adapter."""

    def setUp(self):
        """Set up test data."""
        self.job = Mock()
        self.job.logger = Mock()
        self.sync = Mock()

        # Create mock client
        self.mock_client = MockForwardNetworksClient(
            base_url="https://test.forwardnetworks.com", username="test", password="test"
        )

        self.adapter = ForwardNetworksAdapter(
            job=self.job, sync=self.sync, client=self.mock_client, network_id="network-1"
        )

    def test_load_networks(self):
        """Test loading networks from Forward Networks."""
        self.adapter.load_networks()

        # Check that networks were loaded
        networks = self.adapter.get_all(self.adapter.network)
        self.assertEqual(len(networks), 1)

        network = networks[0]
        self.assertEqual(network.name, "Production Network")
        self.assertEqual(network.network_id, "network-1")

    def test_load_locations(self):
        """Test loading locations from Forward Networks."""
        # First load networks
        self.adapter.load_networks()
        # Then load locations
        self.adapter.load_locations()

        # Check that locations were loaded
        locations = self.adapter.get_all(self.adapter.location)
        self.assertEqual(len(locations), 2)

        # Check first location
        ny_location = None
        for loc in locations:
            if loc.name == "New York DC":
                ny_location = loc
                break

        self.assertIsNotNone(ny_location)
        self.assertEqual(ny_location.location_id, "location-1")
        self.assertEqual(ny_location.latitude, 40.7128)
        self.assertEqual(ny_location.longitude, -74.0060)

    def test_load_devices(self):
        """Test loading devices from Forward Networks."""
        # Load dependencies first
        self.adapter.load_networks()
        self.adapter.load_locations()
        self.adapter.load_devices()

        # Check that devices were loaded
        devices = self.adapter.get_all(self.adapter.device)
        self.assertEqual(len(devices), 3)

        # Check specific device
        core_switch = None
        for dev in devices:
            if dev.name == "ny-core-sw01":
                core_switch = dev
                break

        self.assertIsNotNone(core_switch)
        self.assertEqual(core_switch.manufacturer, "Cisco")
        self.assertEqual(core_switch.model, "Nexus 9000")
        self.assertEqual(core_switch.serial_number, "FCH12345678")
        self.assertEqual(core_switch.primary_ip, "192.168.100.10")

    def test_load_interfaces(self):
        """Test loading interfaces from Forward Networks."""
        # Load dependencies
        self.adapter.load_networks()
        self.adapter.load_locations()
        self.adapter.load_devices()
        self.adapter.load_interfaces()

        # Check that interfaces were loaded
        interfaces = self.adapter.get_all(self.adapter.interface)
        # Should have at least some interfaces from the mock data
        self.assertGreater(len(interfaces), 0)

    def test_load_ip_data(self):
        """Test loading IP data using NQE queries."""
        # The mock client already returns appropriate data
        # Load dependencies
        self.adapter.load_networks()
        self.adapter.load_locations()
        self.adapter.load_devices()
        self.adapter.load_interfaces()
        self.adapter.load_ip_data()

        # Check that IP addresses were loaded
        ip_addresses = self.adapter.get_all(self.adapter.ip_address)
        self.assertGreater(len(ip_addresses), 0)

        # Check that prefixes were created
        prefixes = self.adapter.get_all(self.adapter.prefix)
        self.assertGreater(len(prefixes), 0)

    def test_load_vlans(self):
        """Test loading VLANs using NQE queries."""
        # The mock client already returns appropriate data
        self.adapter.load_vlans()

        # Check that VLANs were loaded
        vlans = self.adapter.get_all(self.adapter.vlan)
        self.assertEqual(len(vlans), 4)

        # Check specific VLAN
        prod_vlan = None
        for vlan in vlans:
            if vlan.vid == 100:
                prod_vlan = vlan
                break

        self.assertIsNotNone(prod_vlan)
        self.assertEqual(prod_vlan.name, "production")

    def test_full_load(self):
        """Test full data loading process."""
        with patch.object(self.mock_client.nqe, "run_query") as mock_nqe:
            # Setup mock responses
            from .fixtures import MOCK_NQE_IP_QUERY_RESULT, MOCK_NQE_VLAN_QUERY_RESULT

            mock_nqe.side_effect = [MOCK_NQE_IP_QUERY_RESULT, MOCK_NQE_VLAN_QUERY_RESULT]

            # Run full load
            self.adapter.load()

            # Verify all data types were loaded
            networks = self.adapter.get_all(self.adapter.network)
            locations = self.adapter.get_all(self.adapter.location)
            devices = self.adapter.get_all(self.adapter.device)

            self.assertGreater(len(networks), 0)
            self.assertGreater(len(locations), 0)
            self.assertGreater(len(devices), 0)


class TestNautobotAdapter(TestCase):
    """Test Nautobot adapter."""

    def setUp(self):
        """Set up test data."""
        self.job = Mock()
        self.job.logger = Mock()
        self.sync = Mock()

        # Create some test Nautobot objects
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.manufacturer = Manufacturer.objects.create(name="Cisco")
        self.location_type = LocationType.objects.create(name="Site")
        self.location = Location.objects.create(
            name="Test Location", location_type=self.location_type, status=self.status_active
        )
        self.device_type = DeviceType.objects.create(model="Test Model", manufacturer=self.manufacturer)
        self.namespace, _ = Namespace.objects.get_or_create(name="Global")

        self.adapter = NautobotAdapter(job=self.job, sync=self.sync)

    def test_status_active_property(self):
        """Test status_active property."""
        status = self.adapter.status_active
        self.assertEqual(status.name, "Active")

    def test_get_or_create_tag(self):
        """Test tag creation."""
        tag = self.adapter.get_or_create_tag("test-tag")
        self.assertEqual(tag.name, "test-tag")

        # Test getting existing tag
        tag2 = self.adapter.get_or_create_tag("test-tag")
        self.assertEqual(tag.id, tag2.id)

    def test_get_or_create_manufacturer(self):
        """Test manufacturer creation."""
        manufacturer = self.adapter.get_or_create_manufacturer("Arista")
        self.assertEqual(manufacturer.name, "Arista")

        # Test getting existing manufacturer
        manufacturer2 = self.adapter.get_or_create_manufacturer("Cisco")
        self.assertEqual(manufacturer2.id, self.manufacturer.id)


class TestForwardNetworksIntegration(TestCase):
    """Integration tests for Forward Networks sync."""

    def setUp(self):
        """Set up test data."""
        self.job = Mock()
        self.job.logger = Mock()
        self.sync = Mock()

        # Create necessary Nautobot objects
        self.status_active, _ = Status.objects.get_or_create(name="Active")
        self.location_type = LocationType.objects.create(name="Site")
        self.namespace, _ = Namespace.objects.get_or_create(name="Global")

        # Create mock client
        self.mock_client = MockForwardNetworksClient(
            base_url="https://test.forwardnetworks.com", username="test", password="test"
        )

    def test_sync_forward_networks_to_nautobot(self):
        """Test syncing data from Forward Networks to Nautobot."""
        # The mock client already returns appropriate data
        # Create adapters
        source_adapter = ForwardNetworksAdapter(
            job=self.job, sync=self.sync, client=self.mock_client, network_id="network-1"
        )
        target_adapter = NautobotAdapter(job=self.job, sync=self.sync)

        # Load data
        source_adapter.load()
        target_adapter.load()

        # Verify source data was loaded
        networks = source_adapter.get_all(source_adapter.network)
        devices = source_adapter.get_all(source_adapter.device)
        locations = source_adapter.get_all(source_adapter.location)

        self.assertGreater(len(networks), 0)
        self.assertGreater(len(devices), 0)
        self.assertGreater(len(locations), 0)

        # In a real sync, we would perform diff and sync operations here
        # For this test, we just verify the data loading works correctly

    def test_client_connectivity(self):
        """Test Forward Networks client connectivity."""
        # Test basic client operations
        networks = self.mock_client.networks.get_networks()
        self.assertIsInstance(networks, list)
        self.assertGreater(len(networks), 0)

        # Test device retrieval
        devices = self.mock_client.devices.get_devices("network-1")
        self.assertIsInstance(devices, list)
        self.assertGreater(len(devices), 0)

        # Test locations
        locations = self.mock_client.locations.get_locations("network-1")
        self.assertIsInstance(locations, list)
        self.assertGreater(len(locations), 0)
