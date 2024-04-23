"""Itential SSoT API Client Tests."""

from nautobot_ssot.tests.itential.fixtures.base import ItentialSSoTBaseTestCase
from nautobot_ssot.tests.itential.fixtures import gateways


class AutomationGatewayClientTestCase(ItentialSSoTBaseTestCase):
    """Itential Automation Gateway Client Test Cases."""

    def test_login_success(self):
        """Test API client login."""
        response = self.client.login()
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("login"))

    def test_get_devices_success(self):
        """Test get_devices."""
        response = self.client.get_devices()
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("get_devices"))

    def test_get_device_success(self):
        """Test get_device."""
        response = self.client.get_device(device_name="rtr1.example.net")
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("get_device"))

    def test_create_device_success(self):
        """Test create_device."""
        response = self.client.create_device(device_name="rtr10.example.net", variables={})
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("create_device"))

    def test_update_device_success(self):
        """Test update_device."""
        response = self.client.update_device(device_name="rtr10.example.net", variables={})
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("update_device"))

    def test_delete_device_success(self):
        """Test delete_device."""
        response = self.client.delete_device(device_name="rtr10.example.net")
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("delete_device"))

    def test_get_groups_success(self):
        """Test get_groups."""
        response = self.client.get_groups()
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("get_groups"))

    def test_get_group_success(self):
        """Test get_group."""
        response = self.client.get_group(group_name="all")
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("get_group"))

    def test_create_group_success(self):
        """Test create_group."""
        response = self.client.create_group(group_name="test-group", variables={})
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("create_group"))

    def test_update_group_success(self):
        """Test update_group."""
        response = self.client.update_group(group_name="test-group", variables={})
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("update_group"))

    def test_delete_group_success(self):
        """Test delete_group."""
        response = self.client.delete_group(group_name="test-group")
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("delete_group"))

    def test_logout_success(self):
        """Test API client logout."""
        response = self.client.logout()
        self.assertEqual(response, gateways.responses["iag1"]["responses"].get("logout"))
