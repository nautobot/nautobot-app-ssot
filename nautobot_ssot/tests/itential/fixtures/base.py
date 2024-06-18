"""Itential SSoT Base TestCase."""

import os
import unittest
import requests_mock

# from unittest import TestCase

from nautobot.apps.testing import TestCase
from nautobot.apps.testing import TransactionTestCase

from nautobot.extras.models import Status

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.itential.diffsync.adapters import itential, nautobot
from nautobot_ssot.tests.itential.fixtures import gateways, urls, clients, devices


class ItentialSSoTBaseTestCase(TestCase):
    """Itential Automation Gateway Client Test Cases."""

    def setUp(self):
        """Setup test cases."""
        self.job = unittest.mock.MagicMock()
        self.requests_mock = requests_mock.Mocker()
        self.requests_mock.start()

        for device in gateways.gateways:
            os.environ[device.get("username_env")] = "testUser"
            os.environ[device.get("password_env")] = "testPass"
            os.environ[device.get("ansible_vault_env")] = "testAnsibleVaultKey"
            os.environ[device.get("device_user_env")] = "testDeviceUser"
            os.environ[device.get("device_pass_env")] = "testDevicePass"

            gateways.update_or_create_automation_gateways(
                name=device.get("name"),
                description=device.get("description"),
                location=device.get("location"),
                region=device.get("region"),
                gateway=device.get("gateway"),
                enabled=device.get("enabled"),
                username_env=device.get("username_env"),
                password_env=device.get("password_env"),
                ansible_vault_env=device.get("ansible_vault_env"),
                device_user_env=device.get("device_user_env"),
                device_pass_env=device.get("device_pass_env"),
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
                config_context=device.get("config_context"),
            )

        self.status, _ = Status.objects.get_or_create(name="Active")
        self.gateway = AutomationGatewayModel.objects.first()
        self.client = clients.api_client(self.gateway)
        self.itential_adapter = itential.ItentialAnsibleDeviceAdapter(api_client=self.client, job=self.job, sync=None)
        self.nautobot_adapter = nautobot.NautobotAnsibleDeviceAdapter(
            job=self.job, gateway=self.gateway, status=self.status, sync=None
        )

        self.itential_adapter.load()
        self.nautobot_adapter.load()

    def tearDown(self):
        """Teardown test cases."""
        self.requests_mock.stop()


class ItentialSSoTBaseTransactionTestCase(TransactionTestCase):
    """Itential Automation Gateway Client Test Cases."""

    def setUp(self):
        """Setup test cases."""
        self.job = unittest.mock.MagicMock()
        self.requests_mock = requests_mock.Mocker()
        self.requests_mock.start()

        for device in gateways.gateways:
            os.environ[device.get("username_env")] = "testUser"
            os.environ[device.get("password_env")] = "testPass"
            os.environ[device.get("ansible_vault_env")] = "testAnsibleVaultKey"
            os.environ[device.get("device_user_env")] = "testDeviceUser"
            os.environ[device.get("device_pass_env")] = "testDevicePass"

            gateways.update_or_create_automation_gateways(
                name=device.get("name"),
                description=device.get("description"),
                location=device.get("location"),
                region=device.get("region"),
                gateway=device.get("gateway"),
                enabled=device.get("enabled"),
                username_env=device.get("username_env"),
                password_env=device.get("password_env"),
                ansible_vault_env=device.get("ansible_vault_env"),
                device_user_env=device.get("device_user_env"),
                device_pass_env=device.get("device_pass_env"),
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
                config_context=device.get("config_context"),
            )

        self.status, _ = Status.objects.get_or_create(name="Active")
        self.gateway = AutomationGatewayModel.objects.first()
        self.client = clients.api_client(self.gateway)
        self.itential_adapter = itential.ItentialAnsibleDeviceAdapter(api_client=self.client, job=self.job, sync=None)
        self.nautobot_adapter = nautobot.NautobotAnsibleDeviceAdapter(
            job=self.job, gateway=self.gateway, status=self.status, sync=None
        )

        self.itential_adapter.load()
        self.nautobot_adapter.load()

    def tearDown(self):
        """Teardown test cases."""
        self.requests_mock.stop()
