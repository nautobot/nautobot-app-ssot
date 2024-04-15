"""Itential SSoT Base TestCase."""

import os
import requests_mock
from unittest import TestCase

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.tests.itential.fixtures import gateways, logger, urls, clients, devices


class ItentialSSoTBaseTestCase(TestCase):
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
                headers=url_item.get("headers", {}),
                cookies=url_item.get("cookies", {}),
            )

        for device in devices.data:
            devices.update_or_create_device_object(
                status=device.get("status"),
                role=device.get("role"),
                name=device.get("name"),
                location=device.get("location"),
                manufacturer=device.get("manufacturer"),
                platform=device.get("platform"),
                network_driver=device.get("network_driver"),
                model=device.get("model"),
                interface=device.get("interface"),
                ip_address=device.get("ip_address"),
            )

        self.gateway = AutomationGatewayModel.objects.first()
        self.client = clients.api_client(self.gateway)

    def tearDown(self):
        """Teardown test cases."""
        self.requests_mock.stop()
