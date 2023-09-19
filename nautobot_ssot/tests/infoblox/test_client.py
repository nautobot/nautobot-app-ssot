"""Unit tests for Infoblox client."""
# pylint: disable=protected-access
# pylint: disable=too-many-public-methods
from collections import namedtuple
from os import path

import unittest
from unittest.mock import patch
import pytest
from requests.models import HTTPError
import requests_mock

from nautobot_ssot.integrations.infoblox.utils.client import InvalidUrlScheme, get_dns_name

from .fixtures_infoblox import (
    get_ptr_record_by_name,
    localhost_client_infoblox,
    get_all_ipv4address_networks,
    get_all_ipv4address_networks_medium,
    get_all_ipv4address_networks_large,
    get_all_ipv4address_networks_bulk,
    create_ptr_record,
    create_a_record,
    create_host_record,
    get_host_by_ip,
    get_a_record_by_ip,
    get_a_record_by_name,
    get_host_record_by_name,
    get_all_dns_views,
    get_dhcp_lease_from_ipv4,
    get_dhcp_lease_from_hostname,
    get_all_subnets,
    get_authoritative_zone,
    find_network_reference,
    find_next_available_ip,
    search_ipv4_address,
    LOCALHOST,
)

Origin = namedtuple("Origin", ["name", "slug"])

# Setup Mock information
HERE = path.abspath(path.dirname(__file__))

API_CALLS = [
    {
        "url": "https://mocktower/api/v2/inventories/",
        "fixture": f"{HERE}/fixtures/get_all_ipv4_address_networks.json",
        "method": "get",
    },
]

SLACK_ORIGIN = Origin(name="Slack", slug="slack")


class TestInfobloxTest(unittest.TestCase):
    """Test Version is the same."""

    def setUp(self) -> None:
        self.infoblox_client = localhost_client_infoblox(LOCALHOST)

    def test_urlparse_without_protocol(self):
        """Test urlparse returns HTTPS when only URL sent."""
        infoblox_client = localhost_client_infoblox("mock_url.com")
        self.assertEqual(infoblox_client.url, "https://mock_url.com")

    def test_urlparse_with_http_protocol(self):
        """Test urlparse returns HTTPS when HTTP protocol sent."""
        infoblox_client = localhost_client_infoblox("http://mock_url.com")
        self.assertEqual(infoblox_client.url, "https://mock_url.com")

    def test_urlparse_with_https_protocol(self):
        """Test urlparse returns HTTPS when HTTPS protocol sent."""
        infoblox_client = localhost_client_infoblox("https://mock_url.com")
        self.assertEqual(infoblox_client.url, "https://mock_url.com")

    def test_urlparse_with_file_protocol(self):
        """Test urlparse returns HTTPS when file link sent."""
        with self.assertRaises(InvalidUrlScheme):
            localhost_client_infoblox("file://mock_file.txt")
        self.assertLogs("Invalid URL scheme 'file' found for Infoblox URL. Please correct to use HTTPS.")

    def test_get_dns_name(self):
        """Test that get_dns_name method returns what we expect."""
        tests = {
            "www.test.com": "www.test.com",
            "ServerName (Dev)": "ServerName_Dev",
            "Test Printer": "Test_Printer",
            "(TEST)": "",
        }
        for fqdn, expected in tests.items():
            results = get_dns_name(possible_fqdn=fqdn)
            self.assertEqual(results, expected)

    def test_request_success_generic(self):
        """Test generic _request with OK status."""
        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/test_url")
            resp = self.infoblox_client._request("GET", "test_url")
        self.assertEqual(resp.status_code, 200)

    def test_request_with_headers(self):
        """Test request header contents."""

        def check_headers(request):
            """Check all header fields except authentication"""
            unittest.TestCase.assertEqual(unittest.TestCase(), request.headers["Accept-Encoding"], "gzip, deflate")
            unittest.TestCase.assertEqual(unittest.TestCase(), request.headers["Accept"], "*/*")
            unittest.TestCase.assertEqual(unittest.TestCase(), request.headers["Connection"], "keep-alive")
            unittest.TestCase.assertEqual(unittest.TestCase(), request.headers["Content-type"], "application/json")

            return True

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/test_url", additional_matcher=check_headers)
            resp = self.infoblox_client._request("GET", "test_url")
        self.assertEqual(resp.status_code, 200)

    def test_get_all_ipv4_address_networks_success(self):
        """Test get_all_ipv4_address_networks success."""
        mock_prefix = "10.220.0.100/31"
        mock_response = get_all_ipv4address_networks()
        mock_uri = "request"

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_all_ipv4address_networks(prefixes=[(mock_prefix, "default")])

        self.assertEqual(resp, mock_response[0])

    def test_get_all_ipv4_address_networks_failed(self):
        """Test get_all_ipv4_address_networks error."""
        mock_prefix = "10.220.0.100/31"
        mock_response = ""
        mock_uri = "request"

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            response = self.infoblox_client.get_all_ipv4address_networks([(mock_prefix, "default")])

            self.assertEqual(response, [])

    def test_get_all_ipv4_address_networks_medium_data_success(self):
        """Test get_all_ipv4_address_networks success with medium data set."""
        prefixes = [("172.16.0.0/29", "default"), ("10.220.0.100/31", "default")]
        mock_uri = "request"
        response = [get_all_ipv4address_networks_medium()[0] + get_all_ipv4address_networks()[0]]
        with requests_mock.Mocker() as req:
            req.post(
                f"{LOCALHOST}/{mock_uri}",
                json=response,
                status_code=201,
            )
            resp = self.infoblox_client.get_all_ipv4address_networks(prefixes=prefixes)
        expected = get_all_ipv4address_networks_medium()[0] + get_all_ipv4address_networks()[0]
        self.assertEqual(resp, expected)

    def test_get_all_ipv4_address_networks_large_data_success(self):
        """Test get_all_ipv4_address_networks success with large data set."""
        prefixes = [("10.0.0.0/22", "default"), ("10.220.0.100/31", "default")]

        mock_response = [
            {"json": get_all_ipv4address_networks_large(), "status_code": 201},
            {"json": get_all_ipv4address_networks(), "status_code": 201},
        ]
        mock_uri = "request"

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", mock_response)
            resp = self.infoblox_client.get_all_ipv4address_networks(prefixes=prefixes)

        expected = get_all_ipv4address_networks_large()[0] + get_all_ipv4address_networks()[0]
        self.assertEqual(resp, expected)

    def test_get_all_ipv4_address_networks_bulk_data_success(self):
        """Test get_all_ipv4_address_networks success with a bulk data set that exceeds 1k results."""
        prefixes = [("192.168.0.0/23", "default"), ("192.168.2.0/23", "default")]
        mock_uri = "request"
        with requests_mock.Mocker() as req:
            req.post(
                f"{LOCALHOST}/{mock_uri}",
                [
                    {"json": get_all_ipv4address_networks_bulk(), "status_code": 201},
                    {"json": [], "status_code": 201},
                ],
            )
            resp = self.infoblox_client.get_all_ipv4address_networks(prefixes=prefixes)
        self.assertEqual(resp, get_all_ipv4address_networks_bulk()[0])

    def test_get_host_record_by_name_success(self):
        """Test get_host_by_record success."""
        mock_fqdn = "test.fqdn.com"
        mock_response = get_host_record_by_name()
        mock_uri = "record:host"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_host_record_by_name(mock_fqdn)

        self.assertEqual(resp, mock_response["result"])

    def test_get_host_record_by_name_fail(self):
        """Test get_host_by_record success."""
        mock_fqdn = "test.fqdn.com"
        mock_response = ""
        mock_uri = "record:host"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_host_record_by_name(mock_fqdn)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_host_record_by_ip_success(self):
        """Test get_host_by_ip success."""
        mock_ip = "10.10.0.2"
        mock_response = get_host_by_ip()
        mock_uri = "record:host"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_host_record_by_ip(mock_ip)

        self.assertEqual(resp, mock_response["result"])

    def test_get_host_record_by_ip_fail(self):
        """Test get_host_by_ip fail."""
        mock_ip = "10.10.0.2"
        mock_response = ""
        mock_uri = "record:host"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_host_record_by_ip(mock_ip)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_a_record_by_name_success(self):
        """Test get_a_record_by_name success."""
        mock_fqdn = "test.fqdn.com"
        mock_response = get_a_record_by_name()
        mock_uri = "record:a"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_a_record_by_name(mock_fqdn)

        self.assertEqual(resp, mock_response["result"])

    def test_get_a_record_by_name_fail(self):
        """Test get_a_record_by_name fail."""
        mock_fqdn = "test.fqdn.com"
        mock_response = ""
        mock_uri = "record:a"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_a_record_by_name(mock_fqdn)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_a_record_by_ip_success(self):
        """Test get_a_record_by_ip success."""
        mock_ip = "10.10.0.2"
        mock_response = get_a_record_by_ip()
        mock_uri = "record:a"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_a_record_by_ip(mock_ip)

        self.assertEqual(resp, mock_response["result"])

    def test_get_a_record_by_ip_fail(self):
        """Test get_a_record_by_ip fail."""
        mock_ip = "10.10.0.2"
        mock_response = ""
        mock_uri = "record:a"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_a_record_by_ip(mock_ip)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_all_dns_views_success(self):
        """Test get_all_dns_views success."""
        mock_response = get_all_dns_views()
        mock_uri = "view"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_all_dns_views()

        self.assertEqual(resp, mock_response["result"])

    def test_get_all_dns_views_fail(self):
        """Test get_all_dns_views fail."""
        mock_response = ""
        mock_uri = "view"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_all_dns_views()

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_dhcp_lease_from_ipv4_success(self):
        """Test get_dhcp_lease_from_ipv4 success."""
        mock_ip = "10.10.0.2"
        mock_response = get_dhcp_lease_from_ipv4()
        mock_uri = "lease"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_dhcp_lease_from_ipv4(mock_ip)

        self.assertEqual(resp, mock_response)

    def test_get_dhcp_lease_from_ipv4_fail(self):
        """Test get_dhcp_lease_from_ipv4 fail."""
        mock_ip = "10.10.0.2"
        mock_response = ""
        mock_uri = "lease"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_dhcp_lease_from_ipv4(mock_ip)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_dhcp_lease_from_hostname_success(self):
        """Test get_dhcp_lease_from_hostname success."""
        mock_host = "testdevice1.test"
        mock_response = get_dhcp_lease_from_hostname()
        mock_uri = "lease"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_dhcp_lease_from_hostname(mock_host)

        self.assertEqual(resp, mock_response)

    def test_get_dhcp_lease_from_hostname_fail(self):
        """Test get_dhcp_lease_from_hostname fail."""
        mock_host = "testdevice1.test"
        mock_response = ""
        mock_uri = "lease"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_dhcp_lease_from_hostname(mock_host)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_all_subnets_success(self):
        """Test get_all_subnets success."""
        mock_response = get_all_subnets()
        mock_uri = "network"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_all_subnets()

        self.assertEqual(resp, mock_response["result"])

    def test_get_all_subnets_fail(self):
        """Test get_all_subnets fail."""
        mock_response = ""
        mock_uri = "network"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            response = self.infoblox_client.get_all_subnets()

        self.assertEqual(response, [])

    def test_get_authoritative_zone_success(self):
        """Test get_authoritative_zone success."""
        mock_response = get_authoritative_zone()
        mock_uri = "zone_auth"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_authoritative_zone()

        self.assertEqual(resp, mock_response["result"])

    def test_get_authoritative_zone_fail(self):
        """Test get_authoritative_zone fail."""
        mock_response = ""
        mock_uri = "zone_auth"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_authoritative_zone()

        self.assertEqual(err.value.response.status_code, 404)

    def test_create_ptr_record_success(self):
        mock_uri = "record:ptr"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"

        mock_response = create_ptr_record()
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            resp = self.infoblox_client.create_ptr_record(mock_fqdn, mock_ip_address)
        self.assertEqual(resp, mock_response["result"])

    def test_create_ptr_record_failure(self):
        mock_uri = "record:ptr"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"
        mock_reverse_host = "wrong_reverse_dns"
        mock_payload = {"name": mock_reverse_host, "ptrdname": mock_fqdn, "ipv4addr": mock_ip_address}

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_payload, status_code=404)

            with pytest.raises(HTTPError) as err:
                self.infoblox_client.create_ptr_record(mock_fqdn, mock_ip_address)

        self.assertEqual(err.value.response.status_code, 404)

    def test_create_a_record_success(self):
        mock_uri = "record:a"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"

        mock_response = create_a_record()
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            resp = self.infoblox_client.create_a_record(mock_fqdn, mock_ip_address)

        self.assertEqual(resp, mock_response["result"])

    def test_create_a_record_failure(self):
        mock_uri = "record:a"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json="", status_code=404)

            with pytest.raises(HTTPError) as err:
                self.infoblox_client.create_a_record(mock_fqdn, mock_ip_address)

        self.assertEqual(err.value.response.status_code, 404)

    def test_create_host_record_success(self):
        mock_uri = "record:host"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"

        mock_response = create_host_record()
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            resp = self.infoblox_client.create_host_record(mock_fqdn, mock_ip_address)

        self.assertEqual(resp, mock_response["result"])

    def test_create_host_record_failure(self):
        mock_uri = "record:host"
        mock_fqdn = "test-device.test-site"
        mock_ip_address = "10.1.1.1"

        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json="", status_code=404)
            response = self.infoblox_client.create_host_record(mock_fqdn, mock_ip_address)

        self.assertEqual(response, [])

    @patch("nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi._find_network_reference")
    def test_find_next_available_ip_success(self, mock_find_network_reference):
        test_network = "10.220.0.0/22"
        mock_find_network_reference.return_value = find_network_reference().get("result")
        mock_uri = "network/ZG5zLm5ldHdvcmskMTAuMjIwLjAuMC8yMi8w:10.220.0.0/22/default"

        mock_response = find_next_available_ip()
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            next_ip = self.infoblox_client.find_next_available_ip(test_network)
        print(next_ip)
        self.assertEqual(next_ip, "10.220.0.1")

    @patch("nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi._find_network_reference")
    def test_find_next_available_ip_no_network_reference(self, mock_find_network_reference):
        test_network = "10.220.0.0/22"
        mock_find_network_reference.side_effect = Exception
        mock_uri = ""

        mock_response = ""
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            next_ip = self.infoblox_client.find_next_available_ip(test_network)

        self.assertEqual(next_ip, "")

    @patch("nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi.find_next_available_ip")
    def test_reserve_fixed_address_success(self, mock_find_next_available_ip):
        test_network = "10.220.0.0/22"
        test_mac = "11:22:33:AA:BB:CC"
        mock_find_next_available_ip.return_value = "10.220.0.1"
        mock_uri = "fixedaddress"

        mock_response = {"result": {"ipv4addr": "10.220.0.1"}}
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            reserved_ip = self.infoblox_client.reserve_fixed_address(test_network, test_mac)

        self.assertEqual(reserved_ip, "10.220.0.1")

    @patch("nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi.find_next_available_ip")
    def test_reserve_fixed_address_no_ip(self, mock_find_next_available_ip):
        test_network = "10.220.0.0/22"
        test_mac = "11:22:33:AA:BB:CC"
        mock_find_next_available_ip.return_value = ""
        mock_uri = "fixedaddress"

        mock_response = ""
        with requests_mock.Mocker() as req:
            req.post(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            reserved_ip = self.infoblox_client.reserve_fixed_address(test_network, test_mac)

        self.assertFalse(reserved_ip)

    def test_find_network_reference_success(self):
        """Test find network reference success."""
        mock_uri = "network"
        mock_network = "10.220.0.0/22"

        mock_response = find_network_reference()
        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            resp = self.infoblox_client._find_network_reference(mock_network)

        self.assertEqual(resp["result"], mock_response["result"])

    def test_find_network_reference_none(self):
        """Test find network reference none found."""
        mock_uri = "network"
        mock_network = "10.220.0.0/22"

        mock_response = {"result": []}
        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)

            resp = self.infoblox_client._find_network_reference(mock_network)

        self.assertEqual(resp["result"], mock_response["result"])

    def test_find_network_reference_failure(self):
        """Test find network reference failure."""
        mock_uri = "network"
        mock_network = "10.220.0.0/22"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json="", status_code=404)

            with pytest.raises(HTTPError) as err:
                self.infoblox_client._find_network_reference(mock_network)

        self.assertEqual(err.value.response.status_code, 404)

    def test_get_ptr_record_by_name_success(self):
        """Test get_ptr_record_by_name success."""
        mock_fqdn = "testdevice1.test"
        mock_response = get_ptr_record_by_name()
        mock_uri = "record:ptr"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_ptr_record_by_name(mock_fqdn)

        self.assertEqual(resp, mock_response["result"])

    def test_get_ptr_record_by_name_none(self):
        """Test get_ptr_record_by_name none found."""
        mock_fqdn = "testdevice1.test"
        mock_response = {"result": []}
        mock_uri = "record:ptr"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.get_ptr_record_by_name(mock_fqdn)

        self.assertEqual(resp, mock_response["result"])

    def test_get_ptr_record_by_name_fail(self):
        """Test get_ptr_record_by_name fail."""
        mock_fqdn = "testdevice1.test"
        mock_uri = "record:ptr"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json="", status_code=404)

            with pytest.raises(HTTPError) as err:
                self.infoblox_client.get_ptr_record_by_name(mock_fqdn)

        self.assertEqual(err.value.response.status_code, 404)

    def test_search_ipv4_address_success(self):
        """Test search_ipv4_address success."""
        mock_ip = "10.223.0.42"
        mock_response = search_ipv4_address()
        mock_uri = "search"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=200)
            resp = self.infoblox_client.search_ipv4_address(mock_ip)

        self.assertEqual(resp, mock_response["result"])

    def test_search_ipv4_address_fail(self):
        """Test get_host_by_record success."""
        mock_ip = "10.223.0.42"
        mock_response = ""
        mock_uri = "search"

        with requests_mock.Mocker() as req:
            req.get(f"{LOCALHOST}/{mock_uri}", json=mock_response, status_code=404)
            with pytest.raises(HTTPError) as err:
                self.infoblox_client.search_ipv4_address(mock_ip)

        self.assertEqual(err.value.response.status_code, 404)
