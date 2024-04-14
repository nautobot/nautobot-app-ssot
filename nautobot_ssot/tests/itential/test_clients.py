"""Itential SSoT API Client Tests."""

import os
from unittest import TestCase

from nautobot_ssot.tests.itential.fixtures import gateways, logging


class AutomationGatewayClientTestCase(TestCase):
    """Itential Automation Gateway Client Test Cases."""

    def setUp(self):
        """Setup test cases."""
        self.job = logging.JobLogger()

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

    def test_login__success(self):
        """Test API client login."""
        pass

    def test_logout__success(self):
        """Test API client logout."""
        pass

    def test_get_devices__success(self):
        """Test get_devices."""
        pass

    def test_get_device__success(self):
        """Test get_device."""
        pass

    def test_create_device__success(self):
        """Test create_device."""
        pass

    def test_update_device__success(self):
        """Test update_device."""
        pass

    def test_delete_device__success(self):
        """Test delete_device."""
        pass

    def test_get_groups__success(self):
        """Test get_groups."""
        pass

    def test_get_group__success(self):
        """Test get_group."""
        pass

    def test_create_group__success(self):
        """Test create_group."""
        pass

    def test_update_group__success(self):
        """Test update_group."""
        pass

    def test_delete_group__success(self):
        """Test delete_group."""
        pass

    def tearDown(self):
        """Teardown test cases."""
        pass
