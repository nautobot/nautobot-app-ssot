"""Utility functions for working with Citrix ADM."""

import logging
from unittest.mock import MagicMock, patch

import requests
from nautobot.core.testing import TestCase
from requests.exceptions import HTTPError

from nautobot_ssot.integrations.citrix_adm.utils.citrix_adm import (
    CitrixNitroClient,
    parse_nsip6s,
    parse_nsips,
    parse_version,
    parse_vlan_bindings,
)
from nautobot_ssot.tests.citrix_adm.fixtures import (
    DEVICE_FIXTURE_RECV,
    DEVICE_FIXTURE_SENT,
    NSIP6_FIXTURE_RECV,
    NSIP6_FIXTURE_SENT,
    NSIP_FIXTURE_RECV,
    NSIP_FIXTURE_SENT,
    SITE_FIXTURE_RECV,
    SITE_FIXTURE_SENT,
    VLAN_FIXTURE_RECV,
    VLAN_FIXTURE_SENT,
)

LOGGER = logging.getLogger(__name__)
# pylint: disable=too-many-public-methods


class TestCitrixAdmClient(TestCase):
    """Test the Citrix ADM client and calls."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure common variables for tests."""
        self.base_url = "https://example.com"
        self.user = "user"
        self.password = "password"  # nosec: B105
        self.verify = True
        self.job = MagicMock()
        self.job.debug = True
        self.job.logger.info = MagicMock()
        self.job.logger.warning = MagicMock()
        self.client = CitrixNitroClient(self.base_url, self.user, self.password, self.job, self.verify)

    def test_init(self):
        """Validate the class initializer works as expected."""
        self.assertEqual(self.client.url, self.base_url)
        self.assertEqual(self.client.username, self.user)
        self.assertEqual(self.client.password, self.password)
        self.assertEqual(self.client.verify, self.verify)

    def test_url_updated(self):
        """Validate the URL is updated if a trailing slash is included in URL."""
        self.base_url = "https://example.com/"
        self.client = CitrixNitroClient(self.base_url, self.user, self.password, self.job, self.verify)
        self.assertEqual(self.client.url, self.base_url.rstrip("/"))

    @patch.object(CitrixNitroClient, "request")
    def test_login(self, mock_request):
        """Validate functionality of the login() method success."""
        mock_response = MagicMock()
        mock_response = {"login": [{"sessionid": "1234"}]}
        mock_request.return_value = mock_response
        self.client.login()
        self.assertEqual(self.client.headers["Cookie"], "SESSID=1234; path=/; SameSite=Lax; secure; HttpOnly")

    @patch.object(CitrixNitroClient, "request")
    def test_login_failure(self, mock_request):
        """Validate functionality of the login() method failure."""
        mock_response = MagicMock()
        mock_response = {}
        mock_request.return_value = mock_response
        with self.assertRaises(requests.exceptions.RequestException):
            self.client.login()
        self.job.logger.error.assert_called_once_with(
            "Error while logging into Citrix ADM. Please validate your configuration is correct."
        )

    @patch.object(CitrixNitroClient, "request")
    def test_logout(self, mock_request):
        """Validate functionality of the logout() method success."""
        self.client.logout()
        mock_request.assert_called_with(
            method="POST",
            endpoint="config",
            objecttype="logout",
            data="object={'logout': {'username': 'user', 'password': 'password'}}",
        )

    @patch("nautobot_ssot.integrations.citrix_adm.utils.citrix_adm.requests.request")
    def test_request(self, mock_request):
        """Validate functionality of the request() method success."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"errorcode": 0}
        mock_request.return_value = mock_response

        endpoint = "example"
        objecttype = "sample"
        objectname = "test"
        params = {"param1": "value1", "param2": "value2"}
        data = '{"key": "value"}'

        response = self.client.request("POST", endpoint, objecttype, objectname, params, data)

        mock_request.assert_called_with(
            method="POST",
            url="https://example.com/nitro/v1/example/sample/test?param1=value1param2=value2",
            data='{"key": "value"}',
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=60,
            verify=True,
        )
        mock_response.raise_for_status.assert_called_once()
        self.assertEqual(response, {"errorcode": 0})

    @patch("nautobot_ssot.integrations.citrix_adm.utils.citrix_adm.requests.request")
    def test_request_failure(self, mock_request):
        """Validate functionality of the request() method failure."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.raise_for_status.side_effect = HTTPError
        mock_request.return_value = mock_response

        endpoint = "example"
        objecttype = "sample"
        objectname = "test"
        params = "test"
        data = '{"key": "value"}'

        with self.assertRaises(requests.exceptions.HTTPError):
            result = self.client.request("POST", endpoint, objecttype, objectname, params, data)
            self.assertEqual(result, {})
        mock_response.raise_for_status.assert_called_once()

    @patch.object(CitrixNitroClient, "request")
    def test_get_sites_success(self, mock_request):
        """Validate functionality of the get_sites() method success."""
        mock_request.return_value = SITE_FIXTURE_SENT
        expected = self.client.get_sites()
        self.assertEqual(SITE_FIXTURE_RECV, expected)

    @patch.object(CitrixNitroClient, "request")
    def test_get_sites_failure(self, mock_request):
        """Validate functionality of the get_sites() method failure."""
        mock_request.return_value = {}
        expected = self.client.get_sites()
        self.job.logger.error.assert_called_once_with("Error getting sites from Citrix ADM.")
        self.assertEqual(expected, {})

    @patch.object(CitrixNitroClient, "request")
    def test_get_devices_success(self, mock_request):
        """Validate functionality of the get_devices() method success."""
        mock_request.return_value = DEVICE_FIXTURE_SENT
        expected = self.client.get_devices()
        self.assertEqual(DEVICE_FIXTURE_RECV, expected)

    @patch.object(CitrixNitroClient, "request")
    def test_get_devices_failure(self, mock_request):
        """Validate functionality of the get_devices() method failure."""
        mock_request.return_value = {}
        expected = self.client.get_devices()
        self.job.logger.error.assert_called_once_with("Error getting devices from Citrix ADM.")
        self.assertEqual(expected, {})

    @patch.object(CitrixNitroClient, "request")
    def test_get_nsip_success(self, mock_request):
        """Validate functionality of the get_nsip6() method success."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.return_value = NSIP_FIXTURE_SENT
        expected = self.client.get_nsip(adc)
        self.assertEqual(NSIP_FIXTURE_RECV, expected)

    @patch.object(CitrixNitroClient, "request")
    def test_get_nsip_failure(self, mock_request):
        """Validate functionality of the get_nsip() method failure."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.return_value = {}
        actual = self.client.get_nsip(adc)
        self.job.logger.error.assert_called_once_with("Error getting nsip from test")
        self.assertEqual(actual, {})

    @patch.object(CitrixNitroClient, "request")
    def test_get_nsip6_success(self, mock_request):
        """Validate functionality of the get_nsip() method success."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.side_effect = NSIP6_FIXTURE_SENT
        for expected in NSIP6_FIXTURE_RECV:
            actual = self.client.get_nsip6(adc)
            self.assertEqual(actual, expected)

    @patch.object(CitrixNitroClient, "request")
    def test_get_nsip6_failure(self, mock_request):
        """Validate functionality of the get_nsip6() method failure."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.return_value = {}
        actual = self.client.get_nsip6(adc)
        self.job.logger.error.assert_called_once_with("Error getting nsip6 from test")
        self.assertEqual(actual, {})

    @patch.object(CitrixNitroClient, "request")
    def test_get_vlan_bindings_success(self, mock_request):
        """Validate functionality of the get_vlan_bindings() method success."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.side_effect = VLAN_FIXTURE_SENT
        for expected in VLAN_FIXTURE_RECV:
            actual = self.client.get_vlan_bindings(adc)
            self.assertEqual(actual, expected)

    @patch.object(CitrixNitroClient, "request")
    def test_get_vlan_bindings_failure(self, mock_request):
        """Validate functionality of the get_vlan_bindings() method failure."""
        adc = {"hostname": "test", "ip_address": ""}
        mock_request.return_value = {}
        actual = self.client.get_vlan_bindings(adc)
        self.job.logger.error.assert_called_once_with("Error getting vlan bindings from test")
        self.assertEqual(actual, {})

    def test_parse_version(self):
        """Validate functionality of the parse_version function."""
        version = "NetScaler NS13.1: Build 37.38.nc, Date: Nov 23 2022, 04:42:36   (64-bit)"
        expected = "NS13.1: Build 37.38.nc"
        actual = parse_version(version=version)
        self.assertEqual(actual, expected)

    def test_parse_vlan_bindings(self):
        """Validate functionality of the parse_vlan_bindings function."""
        vlan_bindings = VLAN_FIXTURE_RECV[0]
        adc = {"hostname": "test", "ip_address": "192.168.0.1", "netmask": "255.255.255.0"}
        actual = parse_vlan_bindings(vlan_bindings=vlan_bindings, adc=adc, job=self)
        expected = [{"ipaddress": "192.168.0.1", "netmask": 24, "port": "10/1", "version": 4, "vlan": "80"}]
        self.assertEqual(actual, expected)

    def test_parse_nsips(self):
        """Validate functionality of the parse_nsips function."""
        nsips = NSIP_FIXTURE_RECV
        adc = {"hostname": "test", "mgmt_ip_address": "192.168.0.2"}
        ports = [{"ipaddress": "192.168.0.1", "netmask": 24, "port": "10/1", "version": 4, "vlan": "80"}]
        expected = [
            {"ipaddress": "192.168.0.1", "netmask": 24, "tags": ["NSIP"], "port": "10/1", "version": 4, "vlan": "80"},
            {"ipaddress": "192.168.0.2", "netmask": 24, "tags": ["MGMT"], "port": "10/1", "version": 4, "vlan": "80"},
        ]
        actual = parse_nsips(nsips=nsips, adc=adc, ports=ports)
        self.assertEqual(actual, expected)

    def test_parse_nsip6s(self):
        """Validate functionality of the parse_nsip6s function."""
        nsip6s = NSIP6_FIXTURE_RECV[0]
        ports = []
        expected = [{"ipaddress": "fe80::1234:5678:9abc:dev1", "netmask": "64", "port": "L0/1", "vlan": "1"}]
        actual = parse_nsip6s(nsip6s=nsip6s, ports=ports)
        self.assertEqual(actual, expected)
