"""Itential SSoT API Client Tests."""

from unittest.mock import MagicMock, patch

from nautobot_ssot.integrations.itential.clients import retry
from nautobot_ssot.tests.itential.fixtures import gateways
from nautobot_ssot.tests.itential.fixtures.base import ItentialSSoTBaseTestCase


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


class RetryDecoratorTest(ItentialSSoTBaseTestCase):
    """Retry Decorator Test Cases."""

    def test_retry_success_on_first_try(self):
        call_mock = MagicMock(return_value="success")

        @retry(Exception, delay=0, tries=3, backoff=2)
        def func():
            return call_mock()

        result = func()
        self.assertEqual(result, "success")
        call_mock.assert_called_once()

    def test_retry_eventually_succeeds(self):
        call_mock = MagicMock(side_effect=[Exception("fail"), "success"])

        @retry(Exception, delay=0, tries=2, backoff=2)
        def func():
            return call_mock()

        result = func()
        self.assertEqual(result, "success")
        self.assertEqual(call_mock.call_count, 2)

    def test_retry_raises_after_retries(self):
        call_mock = MagicMock(side_effect=Exception("fail"))

        @retry(Exception, delay=0, tries=2, backoff=2)
        def func():
            return call_mock()

        with self.assertRaises(Exception):
            func()
        self.assertEqual(call_mock.call_count, 2)

    @patch("time.sleep", return_value=None)
    def test_retry_respects_delay_and_backoff(self, sleep_mock):
        call_mock = MagicMock(side_effect=[Exception("fail"), Exception("fail"), "success"])

        @retry(Exception, delay=1, tries=3, backoff=2)
        def func():
            return call_mock()

        result = func()
        self.assertEqual(result, "success")
        self.assertEqual(call_mock.call_count, 3)
        # Should sleep twice: first for 1, then for 2 (backoff)
        self.assertEqual(sleep_mock.call_count, 2)
