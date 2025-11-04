"""Utility functions for vSphere tests."""


def _get_virtual_machine_dict(attrs):
    """Build dict used for creating diffsync Virtual Machine."""
    virtual_machine_dict = {
        "status__name": "Active",
        "vcpus": 3,
        "memory": 4096,
        "disk": 50,
        "cluster__name": "TestCluster",
        "primary_ip4__host": None,
        "primary_ip6__host": None,
    }
    virtual_machine_dict.update(attrs)
    return virtual_machine_dict


def _get_virtual_machine_interface_dict(attrs):
    """Build dict used for creating diffsync VM Interface."""
    vm_interface_dict = {
        "enabled": True,
        "status__name": "Active",
        "mac_address": "AA:BB:CC:DD:EE:FF",
    }
    vm_interface_dict.update(attrs)
    return vm_interface_dict
