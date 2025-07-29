"""Test OpenShift client."""

# pylint: disable=protected-access
import os
import unittest
from unittest.mock import Mock, MagicMock, patch

import requests
import responses
from kubernetes import client
from kubernetes.client.rest import ApiException

from nautobot_ssot.integrations.openshift.utilities.openshift_client import (
    OpenshiftClient,
    parse_openshift_url,
)

from .openshift_fixtures import (
    LOCALHOST,
    json_fixture,
    localhost_client_openshift,
    real_path,
)

FIXTURES = os.environ.get("FIXTURE_DIR", real_path)


class TestOpenshiftClient(unittest.TestCase):
    """Test Base OpenShift Client and Calls."""

    @patch.object(client.CoreV1Api, "get_api_resources")
    def setUp(self, mock_get_api):  # pylint:disable=arguments-differ
        """Setup."""
        mock_get_api.return_value = Mock()
        self.client = localhost_client_openshift(LOCALHOST)

    def test_init_success(self):
        """Assert proper initialization of client."""
        self.assertEqual(self.client.url, "https://api.openshift.local:6443")
        self.assertEqual(self.client.api_token, "test-token-12345")
        self.assertFalse(self.client.verify_ssl)
        self.assertIsInstance(self.client.core_v1, client.CoreV1Api)
        self.assertIsInstance(self.client.apps_v1, client.AppsV1Api)
        self.assertIsInstance(self.client.custom_objects, client.CustomObjectsApi)

    def test_parse_openshift_url(self):
        """Test URL parsing function."""
        result = parse_openshift_url("https://api.cluster.example.com:6443")
        self.assertEqual(result["scheme"], "https")
        self.assertEqual(result["hostname"], "api.cluster.example.com")
        self.assertEqual(result["port"], 6443)
        
        # Test default port
        result = parse_openshift_url("https://api.cluster.example.com")
        self.assertEqual(result["port"], 6443)

    @patch.object(client.CoreV1Api, "get_api_resources")
    def test_verify_connection_success(self, mock_get_api):
        """Test successful connection verification."""
        mock_get_api.return_value = Mock()
        self.assertTrue(self.client.verify_connection())

    @patch.object(client.CoreV1Api, "get_api_resources")
    def test_verify_connection_failure(self, mock_get_api):
        """Test failed connection verification."""
        mock_get_api.side_effect = ApiException()
        self.assertFalse(self.client.verify_connection())

    def test_is_kubevirt_vm_pod_by_label(self):
        """Test KubeVirt VM detection by label."""
        # Create mock pod with KubeVirt label
        pod = Mock()
        pod.metadata.labels = {"kubevirt.io/domain": "test-vm"}
        pod.spec.containers = []
        
        self.assertTrue(self.client.is_kubevirt_vm_pod(pod))

    def test_is_kubevirt_vm_pod_by_virt_launcher(self):
        """Test KubeVirt VM detection by virt-launcher container."""
        # Create mock pod with virt-launcher container
        pod = Mock()
        pod.metadata.labels = {}
        
        container = Mock()
        container.name = "compute"
        container.command = ["/usr/bin/virt-launcher"]
        
        pod.spec.containers = [container]
        
        self.assertTrue(self.client.is_kubevirt_vm_pod(pod))

    def test_regular_pod_not_vm(self):
        """Test that regular pods are not detected as VMs."""
        # Create mock regular pod
        pod = Mock()
        pod.metadata.labels = {"app": "nginx"}
        
        container = Mock()
        container.name = "nginx"
        container.command = ["nginx"]
        
        pod.spec.containers = [container]
        
        self.assertFalse(self.client.is_kubevirt_vm_pod(pod))

    def test_parse_memory(self):
        """Test memory parsing."""
        self.assertEqual(self.client._parse_memory("1024Mi"), 1024)
        self.assertEqual(self.client._parse_memory("2Gi"), 2048)
        self.assertEqual(self.client._parse_memory("1048576Ki"), 1024)
        self.assertEqual(self.client._parse_memory("1G"), 1024)
        self.assertEqual(self.client._parse_memory(1024), 1024)
        self.assertEqual(self.client._parse_memory("0"), 0)

    def test_parse_storage(self):
        """Test storage parsing."""
        self.assertEqual(self.client._parse_storage("10Gi"), 10)
        self.assertEqual(self.client._parse_storage("10240Mi"), 10)
        self.assertEqual(self.client._parse_storage("10485760Ki"), 10)
        self.assertEqual(self.client._parse_storage(10), 10)

    def test_parse_cpu(self):
        """Test CPU parsing."""
        self.assertEqual(self.client._parse_cpu("1000m"), 1000)
        self.assertEqual(self.client._parse_cpu("2"), 2000)
        self.assertEqual(self.client._parse_cpu(1.5), 1500)
        self.assertEqual(self.client._parse_cpu("500m"), 500)

    @patch.object(client.CustomObjectsApi, "list_cluster_custom_object")
    def test_check_kubevirt_apis_available(self, mock_list):
        """Test KubeVirt API availability check - available."""
        mock_list.return_value = {"items": []}
        client_obj = OpenshiftClient("https://test", "token", False)
        self.assertTrue(client_obj.kubevirt_available)

    @patch.object(client.CustomObjectsApi, "list_cluster_custom_object")
    def test_check_kubevirt_apis_not_available(self, mock_list):
        """Test KubeVirt API availability check - not available."""
        mock_list.side_effect = ApiException()
        client_obj = OpenshiftClient("https://test", "token", False)
        self.assertFalse(client_obj.kubevirt_available)

    @patch.object(client.CoreV1Api, "list_namespace")
    def test_get_projects(self, mock_list):
        """Test getting projects/namespaces."""
        # Create mock namespace
        ns = Mock()
        ns.metadata.name = "test-namespace"
        ns.metadata.uid = "uuid-123"
        ns.metadata.annotations = {
            "openshift.io/display-name": "Test Namespace",
            "openshift.io/description": "Test Description"
        }
        ns.metadata.labels = {"env": "test"}
        ns.status.phase = "Active"
        
        mock_list.return_value.items = [ns]
        
        projects = self.client.get_projects()
        
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "test-namespace")
        self.assertEqual(projects[0]["uuid"], "uuid-123")
        self.assertEqual(projects[0]["display_name"], "Test Namespace")
        self.assertEqual(projects[0]["description"], "Test Description")
        self.assertEqual(projects[0]["status"], "Active")

    @patch.object(client.CoreV1Api, "list_namespace")
    def test_get_projects_with_filter(self, mock_list):
        """Test getting projects with namespace filter."""
        # Create mock namespaces
        ns1 = Mock()
        ns1.metadata.name = "prod-namespace"
        ns1.metadata.uid = "uuid-1"
        ns1.metadata.annotations = None
        ns1.metadata.labels = {}
        ns1.status.phase = "Active"
        
        ns2 = Mock()
        ns2.metadata.name = "dev-namespace"
        ns2.metadata.uid = "uuid-2"
        ns2.metadata.annotations = None
        ns2.metadata.labels = {}
        ns2.status.phase = "Active"
        
        mock_list.return_value.items = [ns1, ns2]
        
        # Test with filter
        projects = self.client.get_projects(namespace_filter="^prod-.*")
        
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "prod-namespace")

    def test_get_node_role(self):
        """Test node role detection."""
        # Master node
        node = Mock()
        node.metadata.labels = {"node-role.kubernetes.io/master": ""}
        self.assertEqual(self.client._get_node_role(node), "master")
        
        # Control plane node
        node.metadata.labels = {"node-role.kubernetes.io/control-plane": ""}
        self.assertEqual(self.client._get_node_role(node), "master")
        
        # Worker node
        node.metadata.labels = {}
        self.assertEqual(self.client._get_node_role(node), "worker")

    def test_is_node_ready(self):
        """Test node ready status check."""
        # Ready node
        node = Mock()
        condition = Mock()
        condition.type = "Ready"
        condition.status = "True"
        node.status.conditions = [condition]
        self.assertTrue(self.client._is_node_ready(node))
        
        # Not ready node
        condition.status = "False"
        self.assertFalse(self.client._is_node_ready(node))
        
        # No conditions
        node.status.conditions = []
        self.assertFalse(self.client._is_node_ready(node)) 