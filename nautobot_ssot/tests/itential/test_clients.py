"""Itential SSoT API Client Tests."""

import os
import requests_mock
from unittest import TestCase

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.tests.itential.fixtures import gateways, logger, urls, clients


class AutomationGatewayClientTestCase(TestCase):
    """Itential Automation Gateway Client Test Cases."""

    def setUp(self):
        """Setup test cases."""
        self.job = logger.JobLogger()
        self.requests_mock = requests_mock.Mocker()
        self.requests_mock.start()

        for device in gateways.gateways:
            os.environ[device.get("username_env")] = "testUser"
            os.environ[device.get("password_env")] = "testPass"

            gateways.update_or_create_automation_gateways(
                name=device.get("name"),
                description=device.get("description"),
                location=device.get("location"),
                region=device.get("region"),
                gateway=device.get("gateway"),
                enabled=device.get("enabled"),
                username_env=device.get("username_env"),
                password_env=device.get("password_env"),
                secret_group=device.get("secret_group"),
            )

        for url_item in urls.data:
            self.requests_mock.register_uri(
                method=url_item.get("method"),
                url=url_item.get("url"),
                json=url_item.get("json"),
                status_code=url_item.get("status_code", 200),
            )

        self.gateway = AutomationGatewayModel.objects.first()
        self.client = clients.api_client(self.gateway)

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

    def tearDown(self):
        """Teardown test cases."""
        self.requests_mock.stop()
