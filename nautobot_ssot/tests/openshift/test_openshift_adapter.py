"""Unit tests for the OpenShift Diffsync adapter class."""

import os
import unittest
from unittest.mock import Mock, MagicMock, patch

from nautobot_ssot.integrations.openshift.diffsync.adapters.adapter_openshift import (
    OpenshiftAdapter,
)

from .openshift_fixtures import create_default_openshift_config, json_fixture, real_path

FIXTURES = os.environ.get("FIXTURE_DIR", real_path)


class TestOpenshiftAdapter(unittest.TestCase):
    """Test cases for OpenshiftAdapter."""

    def setUp(self):
        """Set up test environment."""
        self.config = create_default_openshift_config()
        self.job = Mock()
        self.sync = Mock()
        
        with patch(
            "nautobot_ssot.integrations.openshift.utilities.openshift_client.OpenshiftClient",
            autospec=True,
        ) as mock_client:
            # Configure mock client
            mock_client.return_value.verify_connection.return_value = True
            mock_client.return_value.kubevirt_available = True
            
            self.openshift_adapter = OpenshiftAdapter(
                job=self.job,
                sync=self.sync,
                config=self.config,
            )
            self.mock_client = self.openshift_adapter.client

    def test_adapter_initialization(self):
        """Test adapter initialization."""
        self.assertEqual(self.openshift_adapter.job, self.job)
        self.assertEqual(self.openshift_adapter.sync, self.sync)
        self.assertEqual(self.openshift_adapter.config, self.config)
        self.assertIsNotNone(self.openshift_adapter.client)

    def test_load_projects(self):
        """Test loading projects/namespaces."""
        mock_projects = [
            {
                "name": "test-project",
                "uuid": "uuid-123",
                "display_name": "Test Project",
                "description": "Test Description",
                "status": "Active",
                "labels": {"env": "test"},
                "annotations": {},
            }
        ]
        self.mock_client.get_projects.return_value = mock_projects
        
        self.openshift_adapter._load_projects()
        
        # Verify project was added
        project = self.openshift_adapter.get("openshift_project", "test-project")
        self.assertIsNotNone(project)
        self.assertEqual(project.name, "test-project")
        self.assertEqual(project.display_name, "Test Project")
        self.mock_client.get_projects.assert_called_once_with(self.config.namespace_filter)

    def test_load_projects_with_filter(self):
        """Test loading projects with namespace filter."""
        self.config.namespace_filter = "^prod-.*"
        mock_projects = []
        self.mock_client.get_projects.return_value = mock_projects
        
        self.openshift_adapter._load_projects()
        
        self.mock_client.get_projects.assert_called_once_with("^prod-.*")

    def test_load_nodes(self):
        """Test loading nodes."""
        mock_nodes = [
            {
                "name": "node-01",
                "uuid": "uuid-node-01",
                "hostname": "node-01.example.com",
                "ip_address": "10.0.0.100",
                "os_version": "RHCOS 4.12",
                "container_runtime": "cri-o://1.25.0",
                "cpu_capacity": 16,
                "memory_capacity": 32768,
                "storage_capacity": 500,
                "status": "Ready",
                "role": "worker",
                "labels": {},
                "annotations": {},
            }
        ]
        self.mock_client.get_nodes.return_value = mock_nodes
        
        self.openshift_adapter._load_nodes()
        
        # Verify node was added
        node = self.openshift_adapter.get("openshift_node", "node-01")
        self.assertIsNotNone(node)
        self.assertEqual(node.hostname, "node-01.example.com")
        self.assertEqual(node.role, "worker")

    def test_load_containers_excludes_kubevirt_vms(self):
        """Test loading containers excludes KubeVirt VM pods."""
        mock_pods = [
            {
                "name": "regular-pod",
                "namespace": "default",
                "uuid": "uuid-1",
                "is_kubevirt_vm": False,
                "node": "node-01",
                "status": "Running",
                "containers": [],
                "restart_count": 0,
                "ip_address": "10.244.1.100",
                "labels": {},
                "annotations": {},
            },
            {
                "name": "vm-pod",
                "namespace": "default",
                "uuid": "uuid-2",
                "is_kubevirt_vm": True,  # This should be excluded
                "node": "node-01",
                "status": "Running",
                "containers": [],
                "restart_count": 0,
                "ip_address": "10.244.1.101",
                "labels": {"kubevirt.io/domain": "test-vm"},
                "annotations": {},
            }
        ]
        mock_containers = [
            {
                "name": "nginx",
                "pod_name": "regular-pod",
                "namespace": "default",
                "uuid": "uuid-container-1",
                "image": "nginx:latest",
                "cpu_request": 100,
                "memory_request": 128,
                "cpu_limit": 500,
                "memory_limit": 256,
                "status": "Running",
                "ports": [],
                "environment": {},
            }
        ]
        
        self.mock_client.get_pods_and_containers.return_value = (mock_pods, mock_containers)
        
        self.openshift_adapter._load_containers()
        
        # Verify only regular pod was added
        regular_pod = self.openshift_adapter.get("openshift_pod", ["default", "regular-pod"])
        self.assertIsNotNone(regular_pod)
        
        # VM pod should not be added
        vm_pod = self.openshift_adapter.get("openshift_pod", ["default", "vm-pod"])
        self.assertIsNone(vm_pod)
        
        # Verify container was added
        container = self.openshift_adapter.get("openshift_container", ["regular-pod", "default", "nginx"])
        self.assertIsNotNone(container)

    def test_load_virtual_machines(self):
        """Test loading KubeVirt virtual machines."""
        mock_vms = [
            {
                "name": "test-vm",
                "namespace": "vms",
                "uuid": "uuid-vm-1",
                "running": True,
                "node": "node-01",
                "cpu_cores": 4,
                "memory": 8192,
                "disks": [{"name": "disk0", "bus": "virtio"}],
                "interfaces": [{"name": "eth0", "type": "bridge"}],
                "status": "Running",
                "guest_os": "",
                "vmi_uid": "uuid-vmi-1",
                "firmware": {},
                "machine_type": "q35",
                "labels": {},
                "annotations": {},
            }
        ]
        mock_vmi = {
            "name": "test-vm",
            "namespace": "vms",
            "uuid": "uuid-vmi-1",
            "vm_name": "test-vm",
            "phase": "Running",
            "node": "node-01",
            "ip_address": "10.244.2.100",
            "ready": True,
            "live_migratable": True,
            "conditions": [],
            "guest_agent_info": {},
        }
        
        self.mock_client.get_virtual_machines.return_value = mock_vms
        self.mock_client.get_virtual_machine_instance.return_value = mock_vmi
        
        self.openshift_adapter._load_virtual_machines()
        
        # Verify VM was added
        vm = self.openshift_adapter.get("openshift_virtualmachine", ["vms", "test-vm"])
        self.assertIsNotNone(vm)
        self.assertEqual(vm.cpu_cores, 4)
        self.assertEqual(vm.memory, 8192)
        
        # Verify VMI was added
        vmi = self.openshift_adapter.get("openshift_vmi", ["vms", "test-vm"])
        self.assertIsNotNone(vmi)
        self.assertEqual(vmi.ip_address, "10.244.2.100")

    def test_load_deployments(self):
        """Test loading deployments."""
        mock_deployments = [
            {
                "name": "test-deployment",
                "namespace": "default",
                "uuid": "uuid-dep-1",
                "replicas": 3,
                "available_replicas": 3,
                "strategy": "RollingUpdate",
                "selector": {"app": "test"},
                "labels": {},
                "annotations": {},
            }
        ]
        self.mock_client.get_deployments.return_value = mock_deployments
        
        self.openshift_adapter._load_deployments()
        
        # Verify deployment was added
        deployment = self.openshift_adapter.get("openshift_deployment", ["default", "test-deployment"])
        self.assertIsNotNone(deployment)
        self.assertEqual(deployment.replicas, 3)

    def test_load_services(self):
        """Test loading services."""
        mock_services = [
            {
                "name": "test-service",
                "namespace": "default",
                "uuid": "uuid-svc-1",
                "type": "ClusterIP",
                "cluster_ip": "10.96.0.100",
                "external_ips": [],
                "ports": [{"port": 80, "protocol": "TCP"}],
                "selector": {"app": "test"},
                "labels": {},
                "annotations": {},
            }
        ]
        self.mock_client.get_services.return_value = mock_services
        
        self.openshift_adapter._load_services()
        
        # Verify service was added
        service = self.openshift_adapter.get("openshift_service", ["default", "test-service"])
        self.assertIsNotNone(service)
        self.assertEqual(service.type, "ClusterIP")

    def test_load_workload_types_all(self):
        """Test loading with workload_types set to 'all'."""
        self.config.workload_types = "all"
        self.config.sync_containers = True
        self.config.sync_deployments = True
        self.config.sync_kubevirt_vms = True
        
        # Mock all method returns
        self.mock_client.get_pods_and_containers.return_value = ([], [])
        self.mock_client.get_deployments.return_value = []
        self.mock_client.get_virtual_machines.return_value = []
        
        with patch.object(self.openshift_adapter, '_load_projects'), \
             patch.object(self.openshift_adapter, '_load_nodes'), \
             patch.object(self.openshift_adapter, '_load_containers') as mock_containers, \
             patch.object(self.openshift_adapter, '_load_deployments') as mock_deployments, \
             patch.object(self.openshift_adapter, '_load_virtual_machines') as mock_vms, \
             patch.object(self.openshift_adapter, '_load_services'):
            
            self.openshift_adapter.load()
            
            # All workload types should be loaded
            mock_containers.assert_called_once()
            mock_deployments.assert_called_once()
            mock_vms.assert_called_once()

    def test_load_workload_types_containers_only(self):
        """Test loading with workload_types set to 'containers'."""
        self.config.workload_types = "containers"
        self.config.sync_containers = True
        self.config.sync_kubevirt_vms = True
        
        # Mock method returns
        self.mock_client.get_pods_and_containers.return_value = ([], [])
        
        with patch.object(self.openshift_adapter, '_load_projects'), \
             patch.object(self.openshift_adapter, '_load_nodes'), \
             patch.object(self.openshift_adapter, '_load_containers') as mock_containers, \
             patch.object(self.openshift_adapter, '_load_virtual_machines') as mock_vms, \
             patch.object(self.openshift_adapter, '_load_services'):
            
            self.openshift_adapter.load()
            
            # Only containers should be loaded
            mock_containers.assert_called_once()
            mock_vms.assert_not_called()

    def test_load_connection_failure(self):
        """Test load fails when connection verification fails."""
        self.mock_client.verify_connection.return_value = False
        
        with self.assertRaises(Exception) as context:
            self.openshift_adapter.load()
        
        self.assertIn("Failed to connect to OpenShift API", str(context.exception))
        self.job.logger.error.assert_called_with("Failed to connect to OpenShift API") 