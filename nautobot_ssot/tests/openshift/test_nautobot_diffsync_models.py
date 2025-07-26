"""Unit tests for Nautobot-side DiffSync Models."""

import uuid
from unittest.mock import Mock, patch

from django.test import TestCase
from nautobot.extras.models.statuses import Status
from nautobot.tenancy.models import Tenant
from nautobot.dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from nautobot.virtualization.models import Cluster, ClusterType, VirtualMachine
from nautobot.ipam.models import IPAddress, Service

from nautobot_ssot.integrations.openshift.diffsync.models.nautobot import (
    NautobotTenant,
    NautobotCluster,
    NautobotDevice,
    NautobotVirtualMachine,
    NautobotIPAddress,
    NautobotService,
)


class TestNautobotTenantModel(TestCase):
    """Test the NautobotTenant DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.tenant_data = {
            "name": "test-tenant",
            "description": "Test tenant description",
            "custom_fields": {"source": "openshift"},
        }

    def test_create_tenant(self):
        """Test creating tenant model."""
        tenant = NautobotTenant(**self.tenant_data)
        self.assertEqual(tenant.name, "test-tenant")
        self.assertEqual(tenant.description, "Test tenant description")
        self.assertEqual(tenant.custom_fields["source"], "openshift")

    def test_tenant_identifiers(self):
        """Test tenant identifiers."""
        self.assertEqual(NautobotTenant._identifiers, ("name",))

    def test_tenant_attributes(self):
        """Test tenant attributes."""
        self.assertEqual(
            NautobotTenant._attributes,
            ("description", "custom_fields")
        )


class TestNautobotClusterModel(TestCase):
    """Test the NautobotCluster DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.cluster_data = {
            "name": "openshift-kubevirt",
            "cluster_type": "KubeVirt",
            "site": "OpenShift Site",
        }

    def test_create_cluster(self):
        """Test creating cluster model."""
        cluster = NautobotCluster(**self.cluster_data)
        self.assertEqual(cluster.name, "openshift-kubevirt")
        self.assertEqual(cluster.cluster_type, "KubeVirt")
        self.assertEqual(cluster.site, "OpenShift Site")

    def test_cluster_identifiers(self):
        """Test cluster identifiers."""
        self.assertEqual(NautobotCluster._identifiers, ("name",))


class TestNautobotDeviceModel(TestCase):
    """Test the NautobotDevice DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.device_data = {
            "name": "openshift-node-01",
            "device_type": "OpenShift Node",
            "device_role": "Compute Node",
            "site": "OpenShift Site",
            "status": "Active",
            "tenant": None,
            "primary_ip4": "10.0.0.100",
            "custom_fields": {
                "cpu_count": 16,
                "memory_gb": 32,
                "os_version": "RHCOS 4.12"
            },
        }

    def test_create_device(self):
        """Test creating device model."""
        device = NautobotDevice(**self.device_data)
        self.assertEqual(device.name, "openshift-node-01")
        self.assertEqual(device.device_type, "OpenShift Node")
        self.assertEqual(device.primary_ip4, "10.0.0.100")

    def test_device_identifiers(self):
        """Test device identifiers."""
        self.assertEqual(NautobotDevice._identifiers, ("name",))


class TestNautobotVirtualMachineModel(TestCase):
    """Test the NautobotVirtualMachine DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.vm_data = {
            "name": "test-kubevirt-vm",
            "cluster": "openshift-kubevirt",
            "status": "Active",
            "vcpus": 4,
            "memory": 8192,
            "disk": 100,
            "tenant": "test-namespace",
            "primary_ip4": "10.244.1.100",
            "custom_fields": {
                "guest_os": "Ubuntu 20.04",
                "namespace": "test-namespace"
            },
        }

    def test_create_vm(self):
        """Test creating VM model."""
        vm = NautobotVirtualMachine(**self.vm_data)
        self.assertEqual(vm.name, "test-kubevirt-vm")
        self.assertEqual(vm.cluster, "openshift-kubevirt")
        self.assertEqual(vm.vcpus, 4)
        self.assertEqual(vm.memory, 8192)

    def test_vm_identifiers(self):
        """Test VM identifiers."""
        self.assertEqual(
            NautobotVirtualMachine._identifiers,
            ("name", "cluster")
        )


class TestNautobotIPAddressModel(TestCase):
    """Test the NautobotIPAddress DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.ip_data = {
            "host": "10.244.1.100",
            "mask_length": 24,
            "status": "Active",
            "description": "Pod IP",
            "tenant": None,
            "assigned_object_type": "vminterface",
            "assigned_object_id": None,
        }

    def test_create_ip(self):
        """Test creating IP address model."""
        ip = NautobotIPAddress(**self.ip_data)
        self.assertEqual(ip.host, "10.244.1.100")
        self.assertEqual(ip.mask_length, 24)
        self.assertEqual(ip.status, "Active")

    def test_ip_identifiers(self):
        """Test IP address identifiers."""
        self.assertEqual(
            NautobotIPAddress._identifiers,
            ("host", "mask_length")
        )


class TestNautobotServiceModel(TestCase):
    """Test the NautobotService DiffSync model."""

    def setUp(self):
        """Initialize test data."""
        self.service_data = {
            "name": "web-service",
            "port": 80,
            "protocol": "TCP",
            "device": None,
            "virtual_machine": None,
            "description": "Web service from OpenShift",
            "custom_fields": {
                "namespace": "default",
                "service_type": "ClusterIP"
            },
        }

    def test_create_service(self):
        """Test creating service model."""
        service = NautobotService(**self.service_data)
        self.assertEqual(service.name, "web-service")
        self.assertEqual(service.port, 80)
        self.assertEqual(service.protocol, "TCP")

    def test_service_identifiers(self):
        """Test service identifiers."""
        self.assertEqual(
            NautobotService._identifiers,
            ("name", "port", "protocol")
        ) 