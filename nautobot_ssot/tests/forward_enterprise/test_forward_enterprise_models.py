"""Test Forward Enterprise DiffSync models functionality."""

from unittest import TestCase
from unittest.mock import Mock, patch

try:
    from diffsync.exceptions import ObjectCrudException
except ImportError:
    ObjectCrudException = Exception  # Fallback for when diffsync is not available

from nautobot_ssot.integrations.forward_enterprise.diffsync.models import (
    DeviceModel,
    InterfaceModel,
    IPAddressModel,
    LocationModel,
    ManufacturerModel,
    NautobotIPAddressModel,
    NautobotPrefixModel,
    NautobotVLANModel,
    PrefixModel,
    VLANModel,
    VRFModel,
)


class TestForwardEnterpriseModels(TestCase):
    """Test Forward Enterprise DiffSync models."""

    def test_device_model_uid(self):
        """Test DeviceModel unique ID generation."""
        device = DeviceModel(
            name="nsx-manager-6-4_edge-1",
            serial="12345",
            uuid=None,
            device_type__manufacturer__name="VMware",
            device_type__model="NSX Manager",
            role__name="Network Device",
            status__name="Active",
        )
        self.assertEqual(device.get_unique_id(), "nsx-manager-6-4_edge-1")

    def test_device_model_uid_with_uuid(self):
        """Test DeviceModel unique ID generation with UUID."""
        device = DeviceModel(
            name="test-device",
            device_type__manufacturer__name="Cisco",
            device_type__model="ISR4331",
            role__name="router",
            status__name="active",
            serial="12345",
            uuid="123e4567-e89b-12d3-a456-426614174000",
        )
        # DeviceModel uses name as identifier, not UUID
        self.assertEqual(device.get_unique_id(), "test-device")

    def test_vrf_model_uid(self):
        """Test VRFModel unique ID generation."""
        vrf = VRFModel(name="__management__", namespace__name="Global", uuid=None)
        self.assertEqual(vrf.get_unique_id(), "__management____Global")

    def test_vrf_model_uid_special_characters(self):
        """Test VRFModel unique ID generation with special characters."""
        vrf = VRFModel(name="test-vrf_123", namespace__name="Site-A")
        self.assertEqual(vrf.get_unique_id(), "test-vrf_123__Site-A")

    def test_prefix_model_uid(self):
        """Test PrefixModel unique ID generation."""
        prefix = PrefixModel(network="10.100.0.134", prefix_length=31, namespace__name="Global")
        self.assertEqual(prefix.get_unique_id(), "10.100.0.134__31__Global")

    def test_prefix_model_uid_different_namespace(self):
        """Test PrefixModel unique ID generation with different namespace."""
        prefix = PrefixModel(network="192.168.1.0", prefix_length=24, namespace__name="Site-B")
        self.assertEqual(prefix.get_unique_id(), "192.168.1.0__24__Site-B")

    def test_interface_model_uid(self):
        """Test InterfaceModel unique ID generation."""
        interface = InterfaceModel(
            name="eth0",
            device__name="test-device",
            uuid=None,
            enabled=True,
            mgmt_only=False,
            mtu=1500,
            type="1000base-t",
            status__name="Active",
        )
        expected_uid = "eth0__test-device"
        self.assertEqual(interface.get_unique_id(), expected_uid)

    def test_ipaddress_model_uid(self):
        """Test IPAddressModel unique ID generation."""
        ip_address = IPAddressModel(
            host="10.100.0.135", mask_length=31, parent__network="10.100.0.134", parent__prefix_length=31
        )
        expected_uid = "10.100.0.135__31"
        self.assertEqual(ip_address.get_unique_id(), expected_uid)

    def test_location_model_uid(self):
        """Test LocationModel unique ID generation."""
        location = LocationModel(name="Site-A", uuid=None, location_type__name="Site", status__name="Active")
        self.assertEqual(location.get_unique_id(), "Site-A")

    def test_manufacturer_model_uid(self):
        """Test ManufacturerModel unique ID generation."""
        manufacturer = ManufacturerModel(name="Cisco", uuid=None)
        self.assertEqual(manufacturer.get_unique_id(), "Cisco")

    def test_vlan_model_validation(self):
        """Test VLAN model field validation."""
        # Test valid VLAN ID
        vlan = VLANModel(vid=100, name="VLAN100", vlan_group__name="Default", status__name="Active")
        self.assertEqual(vlan.vid, 100)

        # Test VLAN ID range validation
        with self.assertRaises(ValueError):
            VLANModel(
                vid=5000,  # Invalid - exceeds max
                name="InvalidVLAN",
                vlan_group__name="Default",
                status__name="Active",
            )

        with self.assertRaises(ValueError):
            VLANModel(
                vid=0,  # Invalid - below min
                name="InvalidVLAN",
                vlan_group__name="Default",
                status__name="Active",
            )

    def test_device_model_location_validation_success(self):
        """Test DeviceModel location validation with valid location."""
        result = DeviceModel.validate_location("TestLocation")
        self.assertEqual(result, "TestLocation")

    def test_device_model_location_validation_fallback(self):
        """Test DeviceModel location validation with unknown location fallback."""
        # Test None gets normalized to "Unknown"
        result = DeviceModel.validate_location(None)
        self.assertEqual(result, "Unknown")

        # Test empty string gets normalized to "Unknown"
        result = DeviceModel.validate_location("")
        self.assertEqual(result, "Unknown")

        # Test whitespace-only gets normalized to "Unknown"
        result = DeviceModel.validate_location("   ")
        self.assertEqual(result, "Unknown")

        # Test values that should normalize to "Unknown"
        for invalid_value in ["unknown", "null", "none", "UNKNOWN", "NULL", "NONE"]:
            result = DeviceModel.validate_location(invalid_value)
            self.assertEqual(result, "Unknown")

        # Test valid location name is preserved
        result = DeviceModel.validate_location("Site-A")
        self.assertEqual(result, "Site-A")

    def test_nautobot_models_duplicate_handling(self):
        """Test Nautobot model duplicate handling."""
        # Mock adapter and ObjectCrudException
        mock_adapter = Mock()
        mock_adapter.job = Mock()
        mock_adapter.job.logger = Mock()

        # Test IP Address duplicate handling
        with patch("nautobot_ssot.integrations.forward_enterprise.diffsync.models.nautobot.super") as mock_super:
            mock_super().create.side_effect = ObjectCrudException("IP address with this Parent and Host already exists")

            # Provide required identifiers for IPAddress
            ip_ids = {"host": "192.168.1.100", "mask_length": 24}
            result = NautobotIPAddressModel.create(mock_adapter, ip_ids, {})
            # Should handle duplicate gracefully and return None
            self.assertIsNone(result)
            # The duplicate handling doesn't log warnings, just returns None

        # Test Prefix duplicate handling
        with patch("nautobot_ssot.integrations.forward_enterprise.diffsync.models.nautobot.super") as mock_super:
            mock_super().create.side_effect = ObjectCrudException("prefix already exists")

            # Provide required identifiers for Prefix
            prefix_ids = {"network": "192.168.1.0", "prefix_length": 24, "namespace__name": "Global"}
            result = NautobotPrefixModel.create(mock_adapter, prefix_ids, {})
            self.assertIsNone(result)

        # Test VLAN duplicate handling
        with patch("nautobot_ssot.integrations.forward_enterprise.diffsync.models.nautobot.super") as mock_super:
            mock_super().create.side_effect = ObjectCrudException("VLAN with this already exists")

            # Provide required identifiers for VLAN
            vlan_ids = {"vid": 100, "name": "TestVLAN", "vlan_group__name": "Default"}
            result = NautobotVLANModel.create(mock_adapter, vlan_ids, {})
            self.assertIsNone(result)

    def test_models_handle_none_values(self):
        """Test that models handle None values gracefully."""
        # Test that models don't crash with minimal required values
        device = DeviceModel(
            name="test-device",
            device_type__manufacturer__name="Test Manufacturer",
            device_type__model="Test Model",
            role__name="Test Role",
            status__name="Active",
        )
        # Should handle minimal values gracefully
        uid = device.get_unique_id()
        self.assertIsNotNone(uid)
        self.assertEqual(uid, "test-device")

    def test_models_have_required_attributes(self):
        """Test that all models have required DiffSync attributes."""
        models = [DeviceModel, VRFModel, PrefixModel, InterfaceModel, IPAddressModel, LocationModel, ManufacturerModel]

        for model_class in models:
            with self.subTest(model=model_class.__name__):
                # Should have _modelname attribute
                self.assertTrue(hasattr(model_class, "_modelname"))
                # Should have _identifiers attribute
                self.assertTrue(hasattr(model_class, "_identifiers"))
                # Should have get_unique_id method
                self.assertTrue(hasattr(model_class, "get_unique_id"))

    def test_custom_field_annotations(self):
        """Test that models properly use custom field annotations."""
        # Test that models have system_of_record and last_synced_from_sor fields
        device = DeviceModel(
            name="test-device",
            device_type__manufacturer__name="Test Manufacturer",
            device_type__model="Test Model",
            role__name="Test Role",
            status__name="Active",
            system_of_record="Forward Enterprise",
            last_synced_from_sor="2024-01-01T00:00:00Z",
        )

        self.assertEqual(device.system_of_record, "Forward Enterprise")
        self.assertEqual(device.last_synced_from_sor, "2024-01-01T00:00:00Z")

    def test_interface_type_normalization(self):
        """Test interface type normalization in InterfaceModel."""
        with patch(
            "nautobot_ssot.integrations.forward_enterprise.utils.nautobot.normalize_interface_type"
        ) as mock_normalize:
            mock_normalize.return_value = "1000base-t"

            interface = InterfaceModel(
                name="GigabitEthernet0/0/1",
                device__name="test-device",
                type="ethernet",
                status__name="Active",
                enabled=True,
                mgmt_only=False,
                mtu=1500,
            )

            # Verify the type field is set to normalized value
            # The mock function should be called during initialization
            self.assertEqual(interface.type, "1000base-t")  # Should be normalized value

    def test_prefix_model_validation(self):
        """Test PrefixModel validation methods."""
        # Test valid prefix
        prefix = PrefixModel(network="192.168.1.0", prefix_length=24, namespace__name="Global", status__name="Active")

        self.assertEqual(prefix.network, "192.168.1.0")
        self.assertEqual(prefix.prefix_length, 24)

        # Test valid prefix length range (0-32 for IPv4, 0-128 for IPv6)
        # For this test, we'll just verify the model accepts valid values
        prefix_valid = PrefixModel(
            network="192.168.1.0",
            prefix_length=30,  # Valid prefix length
            namespace__name="Global",
            status__name="Active",
        )
        self.assertEqual(prefix_valid.prefix_length, 30)
