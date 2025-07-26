"""Test KubeVirt utilities."""

import unittest

from nautobot_ssot.integrations.openshift.utilities.kubevirt_utils import (
    is_vm_running,
    extract_vm_os_info,
    get_vm_network_interfaces,
    calculate_vm_resources,
)


class TestKubeVirtUtils(unittest.TestCase):
    """Test KubeVirt utility functions."""

    def test_is_vm_running(self):
        """Test VM running status detection."""
        # Running VM
        self.assertTrue(is_vm_running({"printableStatus": "Running"}))
        self.assertTrue(is_vm_running({"printableStatus": "running"}))
        self.assertTrue(is_vm_running({"printableStatus": "Migrating"}))
        self.assertTrue(is_vm_running({"printableStatus": "migrating"}))
        
        # Not running VM
        self.assertFalse(is_vm_running({"printableStatus": "Stopped"}))
        self.assertFalse(is_vm_running({"printableStatus": "Paused"}))
        self.assertFalse(is_vm_running({"printableStatus": "Unknown"}))
        self.assertFalse(is_vm_running({}))

    def test_extract_vm_os_info(self):
        """Test OS info extraction from guest agent data."""
        # Full OS info
        guest_agent_info = {
            "os": {
                "name": "Ubuntu",
                "version": "20.04 LTS"
            }
        }
        self.assertEqual(extract_vm_os_info(guest_agent_info), "Ubuntu 20.04 LTS")
        
        # Only name
        guest_agent_info = {"os": {"name": "CentOS"}}
        self.assertEqual(extract_vm_os_info(guest_agent_info), "CentOS")
        
        # Only version (unlikely but handled)
        guest_agent_info = {"os": {"version": "8.4"}}
        self.assertEqual(extract_vm_os_info(guest_agent_info), "")
        
        # Empty OS info
        self.assertEqual(extract_vm_os_info({"os": {}}), "")
        self.assertEqual(extract_vm_os_info({}), "")
        self.assertEqual(extract_vm_os_info(None), "")

    def test_get_vm_network_interfaces(self):
        """Test network interface extraction from VMI status."""
        # Multiple interfaces
        vmi_status = {
            "interfaces": [
                {
                    "name": "eth0",
                    "mac": "52:54:00:12:34:56",
                    "ipAddress": "10.0.0.100",
                    "ipAddresses": ["10.0.0.100", "fe80::5054:ff:fe12:3456"]
                },
                {
                    "name": "eth1",
                    "mac": "52:54:00:12:34:57",
                    "ipAddress": "192.168.1.100",
                    "ipAddresses": ["192.168.1.100"]
                }
            ]
        }
        
        interfaces = get_vm_network_interfaces(vmi_status)
        self.assertEqual(len(interfaces), 2)
        
        # Check first interface
        self.assertEqual(interfaces[0]["name"], "eth0")
        self.assertEqual(interfaces[0]["mac"], "52:54:00:12:34:56")
        self.assertEqual(interfaces[0]["ip"], "10.0.0.100")
        self.assertEqual(len(interfaces[0]["ips"]), 2)
        
        # Check second interface
        self.assertEqual(interfaces[1]["name"], "eth1")
        self.assertEqual(interfaces[1]["mac"], "52:54:00:12:34:57")
        
        # Empty interfaces
        self.assertEqual(get_vm_network_interfaces({"interfaces": []}), [])
        self.assertEqual(get_vm_network_interfaces({}), [])

    def test_calculate_vm_resources(self):
        """Test VM resource calculation from domain spec."""
        # Full resource spec
        domain_spec = {
            "cpu": {"cores": 4},
            "resources": {
                "requests": {
                    "memory": "8Gi"
                }
            }
        }
        resources = calculate_vm_resources(domain_spec)
        self.assertEqual(resources["cpu_cores"], 4)
        self.assertEqual(resources["memory_mb"], 8192)
        
        # Different memory units
        test_cases = [
            ("4Gi", 4096),
            ("2048Mi", 2048),
            ("1048576Ki", 1024),
        ]
        
        for memory_str, expected_mb in test_cases:
            domain_spec = {
                "resources": {
                    "requests": {"memory": memory_str}
                }
            }
            resources = calculate_vm_resources(domain_spec)
            self.assertEqual(resources["memory_mb"], expected_mb)
        
        # Default values
        resources = calculate_vm_resources({})
        self.assertEqual(resources["cpu_cores"], 1)
        self.assertEqual(resources["memory_mb"], 1024)
        
        # Partial specs
        domain_spec = {"cpu": {"cores": 2}}
        resources = calculate_vm_resources(domain_spec)
        self.assertEqual(resources["cpu_cores"], 2)
        self.assertEqual(resources["memory_mb"], 1024)  # Default 