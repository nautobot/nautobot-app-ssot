"""Itential SSoT API Client Tests."""

from nautobot_ssot.tests.itential.fixtures.base import ItentialSSoTBaseTestCase
from nautobot_ssot.tests.itential.fixtures import gateways


class AutomationGatewayClientTestCase(ItentialSSoTBaseTestCase):
    """Itential Automation Gateway Client Test Cases."""

    def test_login__success(self):
        """Test API client login."""
        response = self.client.login()
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("login"))

    def test_get_devices__success(self):
        """Test get_devices."""
        response = self.client.get_devices()
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("get_devices"))

    def test_get_device__success(self):
        """Test get_device."""
        response = self.client.get_device(device_name="rtr1.example.net")
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("get_device"))

    def test_create_device__success(self):
        """Test create_device."""
        response = self.client.create_device(device_name="rtr10.example.net", variables={})
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("create_device"))

    def test_update_device__success(self):
        """Test update_device."""
        response = self.client.update_device(device_name="rtr10.example.net", variables={})
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("update_device"))

    def test_delete_device__success(self):
        """Test delete_device."""
        response = self.client.delete_device(device_name="rtr10.example.net")
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("delete_device"))

    def test_get_groups__success(self):
        """Test get_groups."""
        response = self.client.get_groups()
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("get_groups"))

    def test_get_group__success(self):
        """Test get_group."""
        response = self.client.get_group(group_name="all")
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("get_group"))

    def test_create_group__success(self):
        """Test create_group."""
        response = self.client.create_group(group_name="test-group", variables={})
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("create_group"))

    def test_update_group__success(self):
        """Test update_group."""
        response = self.client.update_group(group_name="test-group", variables={})
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("update_group"))

    def test_delete_group__success(self):
        """Test delete_group."""
        response = self.client.delete_group(group_name="test-group")
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("delete_group"))

    def test_logout__success(self):
        """Test API client logout."""
        response = self.client.logout()
        self.assertEquals(response, gateways.responses["iag1"]["responses"].get("logout"))
