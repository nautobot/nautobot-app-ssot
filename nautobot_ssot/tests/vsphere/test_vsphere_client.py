"""Test vSphere client."""

# pylint: disable=protected-access
import os
import unittest
from unittest.mock import patch

import requests
import responses
from requests import Session

from nautobot_ssot.integrations.vsphere.utilities.vsphere_client import (
    InvalidUrlScheme,
)

from .vsphere_fixtures import (
    LOCALHOST,
    json_fixture,
    localhost_client_vsphere,
    real_path,
)

FIXTURES = os.environ.get("FIXTURE_DIR", real_path)


class TestVsphere(unittest.TestCase):
    """Test Base vSphere Client and Calls."""

    @patch.object(Session, "post")
    def setUp(self, mock):  # pylint:disable=arguments-differ, unused-argument
        """Setup."""
        self.client = localhost_client_vsphere(LOCALHOST)

    def test_init_success(self):
        """Assert proper initialization of client."""
        self.assertEqual(self.client.vsphere_uri, "https://vcenter.local")
        self.assertTrue(isinstance(self.client.session, requests.Session))
        self.assertFalse(self.client.session.verify)
        expected_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        for key, value in expected_headers.items():
            self.assertIn(key, self.client.session.headers)
            self.assertEqual(self.client.session.headers[key], value)

    @responses.activate
    def test_urlparse_without_protocol(self):
        """Test urlparse returns HTTPS when only URL sent."""
        endpoint = f"{LOCALHOST}/rest/com/vmware/cis/session"
        json_response = json_fixture(f"{FIXTURES}/authentication.json")
        responses.add(
            responses.POST,
            endpoint,
            json=json_response,
            status=200,
        )
        vsphere_client = localhost_client_vsphere("vcenter.local")
        self.assertEqual(vsphere_client.vsphere_uri, "https://vcenter.local")

    @responses.activate
    def test_urlparse_with_http_protocol(self):
        """Test urlparse returns HTTPS when HTTP protocol sent."""
        endpoint = f"{LOCALHOST}/rest/com/vmware/cis/session"
        json_response = json_fixture(f"{FIXTURES}/authentication.json")
        responses.add(
            responses.POST,
            endpoint,
            json=json_response,
            status=200,
        )
        vsphere_client = localhost_client_vsphere("http://vcenter.local")
        self.assertEqual(vsphere_client.vsphere_uri, "https://vcenter.local")

    @responses.activate
    def test_urlparse_with_https_protocol(self):
        """Test urlparse returns HTTPS when HTTPS protocol sent."""
        endpoint = f"{LOCALHOST}/rest/com/vmware/cis/session"
        json_response = json_fixture(f"{FIXTURES}/authentication.json")
        responses.add(
            responses.POST,
            endpoint,
            json=json_response,
            status=200,
        )
        vsphere_client = localhost_client_vsphere("https://vcenter.local")
        self.assertEqual(vsphere_client.vsphere_uri, "https://vcenter.local")

    @responses.activate
    def test_urlparse_with_file_protocol(self):
        """Test urlparse returns HTTPS when file link sent."""
        endpoint = f"{LOCALHOST}/rest/com/vmware/cis/session"
        json_response = json_fixture(f"{FIXTURES}/authentication.json")
        responses.add(
            responses.POST,
            endpoint,
            json=json_response,
            status=200,
        )

        with self.assertRaises(InvalidUrlScheme):
            localhost_client_vsphere("file://vcenter.txt")
        self.assertLogs(
            "Invalid URL scheme 'file' found for vSphere URL. Please correct to use HTTPS."
        )

    @responses.activate
    def test_get_vms(self):
        """Test Get VMs API Call."""
        endpoint = f"{LOCALHOST}/rest/vcenter/vm"
        json_response = json_fixture(f"{FIXTURES}/get_vms.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_vms().json()["value"][0]["memory_size_MiB"], 32768
        )

    @responses.activate
    def test_get_vms_from_cluster(self):
        """Test Get VMs from cluster API Call."""
        cluster = "domain-c1001"
        endpoint = f"{LOCALHOST}/rest/vcenter/vm?filter.clusters={cluster}"
        json_response = json_fixture(f"{FIXTURES}/get_vms_from_cluster.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_vms_from_cluster(cluster).json()["value"][1]["name"],
            "Nautobot",
        )

    @responses.activate
    def test_get_vms_from_dc(self):
        """Test Get VMs from DC API Call."""
        datacenter = "datacenter-62"
        endpoint = f"{LOCALHOST}/rest/vcenter/vm?filter.datacenters={datacenter}"
        json_response = json_fixture(f"{FIXTURES}/get_vms_from_dc.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_vms_from_dc(datacenter).json()["value"][2]["power_state"],
            "POWERED_ON",
        )

    @responses.activate
    def test_get_datacenters(self):
        """Test Get DC's API Call."""
        endpoint = f"{LOCALHOST}/rest/vcenter/datacenter"
        json_response = json_fixture(f"{FIXTURES}/get_datacenters.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_datacenters().json()["value"][0]["name"],
            "CrunchyDatacenter",
        )

    @responses.activate
    def test_get_clusters(self):
        """Test Get Clusters API Call."""
        endpoint = f"{LOCALHOST}/rest/vcenter/cluster"
        json_response = json_fixture(f"{FIXTURES}/get_clusters.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_clusters().json()["value"][0]["name"], "HeshLawCluster"
        )

    @responses.activate
    def test_get_cluster_details(self):
        """Test Get Clusters Detail API Call."""
        cluster_name = "domain-c1001"
        endpoint = f"{LOCALHOST}/rest/vcenter/cluster/{cluster_name}"
        json_response = json_fixture(f"{FIXTURES}/get_cluster_details.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_cluster_details(cluster_name).json()["value"][
                "resource_pool"
            ],
            "resgroup-1002",
        )

    @responses.activate
    def test_get_dc_details(self):
        """Test Get DC Details API Call."""
        datacenter = "datacenter-62"
        endpoint = f"{LOCALHOST}/rest/vcenter/datacenter/{datacenter}"
        json_response = json_fixture(f"{FIXTURES}/get_dc_details.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_datacenter_details(datacenter).json()["value"][
                "datastore_folder"
            ],
            "group-s65",
        )

    @responses.activate
    def test_get_vm_interfaces(self):
        """Test Get VM Interface Details API Call."""
        vm_id = "vm-1012"
        endpoint = f"{LOCALHOST}/rest/vcenter/vm/{vm_id}/guest/networking/interfaces"
        json_response = json_fixture(f"{FIXTURES}/get_vm_interfaces.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_vm_interfaces(vm_id).json()["value"][0]["mac_address"],
            "00:50:56:b5:e5:5f",
        )

    @responses.activate
    def test_get_vm_details(self):
        """Test Get VM Details API Call."""
        vm_id = "vm-1012"
        endpoint = f"{LOCALHOST}/rest/vcenter/vm/{vm_id}"
        json_response = json_fixture(f"{FIXTURES}/get_vm_details.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_vm_details(vm_id).json()["value"]["cpu"]["count"], 4
        )

    @responses.activate
    def test_get_host_from_clusters(self):
        """Test Get host from clusters API Call."""
        cluster = "domain-c1001"
        endpoint = f"{LOCALHOST}/rest/vcenter/host/?filter.clusters={cluster}"
        json_response = json_fixture(f"{FIXTURES}/get_host_from_cluster.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_host_from_cluster(cluster).json()["value"][0]["host"],
            "host-1007",
        )

    @responses.activate
    def test_get_host_details(self):
        """Test Get host details API Call."""
        host = "host-1007"
        endpoint = f"{LOCALHOST}/rest/vcenter/host/?filter.hosts={host}"
        json_response = json_fixture(f"{FIXTURES}/get_host_details.json")

        responses.add(
            responses.GET,
            endpoint,
            json=json_response,
            status=200,
        )
        self.assertEqual(
            self.client.get_host_details(host).json()["value"][0]["name"],
            "crunchy-esxi.heshlaw.local",
        )
