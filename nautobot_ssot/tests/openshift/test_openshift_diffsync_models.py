"""Unit tests for OpenShift SSoT DiffSync Models."""

import uuid
from unittest.mock import MagicMock

from django.test import TestCase
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from nautobot.tenancy.models import Tenant
from nautobot.dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from nautobot.virtualization.models import (
    Cluster,
    ClusterType,
    VirtualMachine,
    VMInterface,
)
from nautobot.ipam.models import IPAddress, Service

from nautobot_ssot.integrations.openshift.diffsync.models.base import (
    OpenshiftProject,
    OpenshiftNode,
)
from nautobot_ssot.integrations.openshift.diffsync.models.containers import (
    OpenshiftPod,
    OpenshiftContainer,
    OpenshiftDeployment,
    OpenshiftService,
)
from nautobot_ssot.integrations.openshift.diffsync.models.kubevirt import (
    OpenshiftVirtualMachine,
    OpenshiftVirtualMachineInstance,
)

from .openshift_fixtures import create_default_openshift_config


def _get_project_dict(attrs=None):
    """Build dict used for creating diffsync Project."""
    project_dict = {
        "name": "test-project",
        "uuid": str(uuid.uuid4()),
        "display_name": "Test Project",
        "description": "Test project description",
        "status": "Active",
        "labels": {"env": "test"},
        "annotations": {},
    }
    if attrs:
        project_dict.update(attrs)
    return project_dict


def _get_node_dict(attrs=None):
    """Build dict used for creating diffsync Node."""
    node_dict = {
        "name": "test-node-01",
        "uuid": str(uuid.uuid4()),
        "hostname": "test-node-01.example.com",
        "ip_address": "10.0.0.100",
        "os_version": "Red Hat Enterprise Linux CoreOS 413.92.202303212039-0",
        "container_runtime": "cri-o://1.26.3",
        "cpu_capacity": 16,
        "memory_capacity": 32768,  # 32GB in MB
        "storage_capacity": 500,  # 500GB
        "status": "Ready",
        "role": "worker",
        "labels": {"node-role.kubernetes.io/worker": ""},
        "annotations": {},
    }
    if attrs:
        node_dict.update(attrs)
    return node_dict


def _get_pod_dict(attrs=None):
    """Build dict used for creating diffsync Pod."""
    pod_dict = {
        "name": "test-pod",
        "namespace": "test-namespace",
        "uuid": str(uuid.uuid4()),
        "node": "test-node-01",
        "containers": [],
        "status": "Running",
        "restart_count": 0,
        "ip_address": "10.244.1.100",
        "labels": {"app": "test-app"},
        "annotations": {},
        "is_kubevirt_vm": False,
    }
    if attrs:
        pod_dict.update(attrs)
    return pod_dict


def _get_container_dict(attrs=None):
    """Build dict used for creating diffsync Container."""
    container_dict = {
        "name": "test-container",
        "pod_name": "test-pod",
        "namespace": "test-namespace",
        "uuid": str(uuid.uuid4()),
        "image": "nginx:latest",
        "cpu_request": 100,  # 100m
        "memory_request": 128,  # 128MB
        "cpu_limit": 500,  # 500m
        "memory_limit": 256,  # 256MB
        "status": "Running",
        "ports": [{"port": 80, "protocol": "TCP", "name": "http"}],
        "environment": {"ENV": "test"},
    }
    if attrs:
        container_dict.update(attrs)
    return container_dict


def _get_virtual_machine_dict(attrs=None):
    """Build dict used for creating diffsync KubeVirt VM."""
    vm_dict = {
        "name": "test-vm",
        "namespace": "test-namespace",
        "uuid": str(uuid.uuid4()),
        "running": True,
        "node": "test-node-01",
        "cpu_cores": 4,
        "memory": 8192,  # 8GB in MB
        "disks": [{"name": "disk0", "bus": "virtio"}],
        "interfaces": [{"name": "eth0", "type": "bridge"}],
        "status": "Running",
        "guest_os": "Ubuntu 20.04",
        "vmi_uid": str(uuid.uuid4()),
        "firmware": {},
        "machine_type": "q35",
        "labels": {"kubevirt.io/domain": "test-vm"},
        "annotations": {},
    }
    if attrs:
        vm_dict.update(attrs)
    return vm_dict


class TestOpenshiftProjectModel(TestCase):
    """Test the OpenshiftProject DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.project_data = _get_project_dict()

    def test_create_project_minimal(self):
        """Test creating project with minimal data."""
        project = OpenshiftProject(**self.project_data)
        self.assertEqual(project.name, "test-project")
        self.assertEqual(project.display_name, "Test Project")
        self.assertEqual(project.status, "Active")

    def test_create_unique_id(self):
        """Test unique ID creation."""
        project = OpenshiftProject(**self.project_data)
        unique_id = project.create_unique_id(**self.project_data)
        self.assertEqual(unique_id, self.project_data["uuid"])
        
        # Test fallback to name
        project_no_uuid = _get_project_dict()
        del project_no_uuid["uuid"]
        unique_id = OpenshiftProject.create_unique_id(**project_no_uuid)
        self.assertEqual(unique_id, "test-project")


class TestOpenshiftNodeModel(TestCase):
    """Test the OpenshiftNode DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.node_data = _get_node_dict()

    def test_create_node(self):
        """Test creating node with full data."""
        node = OpenshiftNode(**self.node_data)
        self.assertEqual(node.name, "test-node-01")
        self.assertEqual(node.hostname, "test-node-01.example.com")
        self.assertEqual(node.ip_address, "10.0.0.100")
        self.assertEqual(node.role, "worker")
        self.assertEqual(node.status, "Ready")

    def test_node_capacity_fields(self):
        """Test node capacity fields."""
        node = OpenshiftNode(**self.node_data)
        self.assertEqual(node.cpu_capacity, 16)
        self.assertEqual(node.memory_capacity, 32768)
        self.assertEqual(node.storage_capacity, 500)

    def test_master_node(self):
        """Test master node creation."""
        master_data = _get_node_dict({
            "name": "master-01",
            "role": "master",
            "labels": {"node-role.kubernetes.io/master": ""}
        })
        node = OpenshiftNode(**master_data)
        self.assertEqual(node.role, "master")


class TestOpenshiftPodModel(TestCase):
    """Test the OpenshiftPod DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.pod_data = _get_pod_dict()

    def test_create_pod(self):
        """Test creating pod."""
        pod = OpenshiftPod(**self.pod_data)
        self.assertEqual(pod.name, "test-pod")
        self.assertEqual(pod.namespace, "test-namespace")
        self.assertEqual(pod.status, "Running")
        self.assertFalse(pod.is_kubevirt_vm)

    def test_pod_identifiers(self):
        """Test pod identifiers are namespace and name."""
        self.assertEqual(OpenshiftPod._identifiers, ("namespace", "name"))

    def test_kubevirt_vm_pod(self):
        """Test pod marked as KubeVirt VM."""
        vm_pod_data = _get_pod_dict({
            "name": "virt-launcher-test-vm",
            "is_kubevirt_vm": True,
            "labels": {"kubevirt.io/domain": "test-vm"}
        })
        pod = OpenshiftPod(**vm_pod_data)
        self.assertTrue(pod.is_kubevirt_vm)


class TestOpenshiftContainerModel(TestCase):
    """Test the OpenshiftContainer DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.container_data = _get_container_dict()

    def test_create_container(self):
        """Test creating container."""
        container = OpenshiftContainer(**self.container_data)
        self.assertEqual(container.name, "test-container")
        self.assertEqual(container.pod_name, "test-pod")
        self.assertEqual(container.namespace, "test-namespace")
        self.assertEqual(container.image, "nginx:latest")

    def test_container_resources(self):
        """Test container resource fields."""
        container = OpenshiftContainer(**self.container_data)
        self.assertEqual(container.cpu_request, 100)
        self.assertEqual(container.memory_request, 128)
        self.assertEqual(container.cpu_limit, 500)
        self.assertEqual(container.memory_limit, 256)

    def test_container_identifiers(self):
        """Test container identifiers."""
        self.assertEqual(
            OpenshiftContainer._identifiers, 
            ("pod_name", "namespace", "name")
        )


class TestOpenshiftDeploymentModel(TestCase):
    """Test the OpenshiftDeployment DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.deployment_data = {
            "name": "test-deployment",
            "namespace": "test-namespace",
            "uuid": str(uuid.uuid4()),
            "replicas": 3,
            "available_replicas": 3,
            "strategy": "RollingUpdate",
            "selector": {"app": "test-app"},
            "labels": {"app": "test-app"},
            "annotations": {},
        }

    def test_create_deployment(self):
        """Test creating deployment."""
        deployment = OpenshiftDeployment(**self.deployment_data)
        self.assertEqual(deployment.name, "test-deployment")
        self.assertEqual(deployment.replicas, 3)
        self.assertEqual(deployment.available_replicas, 3)
        self.assertEqual(deployment.strategy, "RollingUpdate")

    def test_deployment_identifiers(self):
        """Test deployment identifiers."""
        self.assertEqual(
            OpenshiftDeployment._identifiers,
            ("namespace", "name")
        )


class TestOpenshiftServiceModel(TestCase):
    """Test the OpenshiftService DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.service_data = {
            "name": "test-service",
            "namespace": "test-namespace",
            "uuid": str(uuid.uuid4()),
            "type": "ClusterIP",
            "cluster_ip": "10.96.0.100",
            "external_ips": [],
            "ports": [
                {"name": "http", "protocol": "TCP", "port": 80, "target_port": "8080"}
            ],
            "selector": {"app": "test-app"},
            "labels": {"app": "test-app"},
            "annotations": {},
        }

    def test_create_service(self):
        """Test creating service."""
        service = OpenshiftService(**self.service_data)
        self.assertEqual(service.name, "test-service")
        self.assertEqual(service.type, "ClusterIP")
        self.assertEqual(service.cluster_ip, "10.96.0.100")
        self.assertEqual(len(service.ports), 1)

    def test_service_types(self):
        """Test different service types."""
        # NodePort service
        nodeport_data = self.service_data.copy()
        nodeport_data.update({
            "type": "NodePort",
            "ports": [{"port": 80, "node_port": 30080}]
        })
        service = OpenshiftService(**nodeport_data)
        self.assertEqual(service.type, "NodePort")

        # LoadBalancer service
        lb_data = self.service_data.copy()
        lb_data.update({
            "type": "LoadBalancer",
            "external_ips": ["203.0.113.10"]
        })
        service = OpenshiftService(**lb_data)
        self.assertEqual(service.type, "LoadBalancer")
        self.assertEqual(len(service.external_ips), 1)


class TestOpenshiftVirtualMachineModel(TestCase):
    """Test the OpenshiftVirtualMachine DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.vm_data = _get_virtual_machine_dict()

    def test_create_virtual_machine(self):
        """Test creating KubeVirt VM."""
        vm = OpenshiftVirtualMachine(**self.vm_data)
        self.assertEqual(vm.name, "test-vm")
        self.assertEqual(vm.namespace, "test-namespace")
        self.assertTrue(vm.running)
        self.assertEqual(vm.cpu_cores, 4)
        self.assertEqual(vm.memory, 8192)

    def test_vm_is_active(self):
        """Test VM active status check."""
        # Running VM
        vm = OpenshiftVirtualMachine(**self.vm_data)
        self.assertTrue(vm.is_active())

        # Stopped VM
        stopped_data = _get_virtual_machine_dict({
            "running": False,
            "status": "Stopped"
        })
        vm = OpenshiftVirtualMachine(**stopped_data)
        self.assertFalse(vm.is_active())

        # Migrating VM
        migrating_data = _get_virtual_machine_dict({
            "running": True,
            "status": "Migrating"
        })
        vm = OpenshiftVirtualMachine(**migrating_data)
        self.assertTrue(vm.is_active())

    def test_vm_identifiers(self):
        """Test VM identifiers."""
        self.assertEqual(
            OpenshiftVirtualMachine._identifiers,
            ("namespace", "name")
        )


class TestOpenshiftVirtualMachineInstanceModel(TestCase):
    """Test the OpenshiftVirtualMachineInstance DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.vmi_data = {
            "name": "test-vm",
            "namespace": "test-namespace",
            "uuid": str(uuid.uuid4()),
            "vm_name": "test-vm",
            "phase": "Running",
            "node": "test-node-01",
            "ip_address": "10.244.1.200",
            "ready": True,
            "live_migratable": True,
            "conditions": [],
            "guest_agent_info": {
                "os": {"name": "Ubuntu", "version": "20.04"}
            },
            "labels": {},
            "annotations": {},
        }

    def test_create_vmi(self):
        """Test creating VMI."""
        vmi = OpenshiftVirtualMachineInstance(**self.vmi_data)
        self.assertEqual(vmi.name, "test-vm")
        self.assertEqual(vmi.phase, "Running")
        self.assertTrue(vmi.ready)
        self.assertTrue(vmi.live_migratable)

    def test_vmi_phases(self):
        """Test different VMI phases."""
        phases = ["Pending", "Scheduling", "Scheduled", "Running", "Succeeded", "Failed"]
        
        for phase in phases:
            vmi_data = self.vmi_data.copy()
            vmi_data["phase"] = phase
            vmi = OpenshiftVirtualMachineInstance(**vmi_data)
            self.assertEqual(vmi.phase, phase) 