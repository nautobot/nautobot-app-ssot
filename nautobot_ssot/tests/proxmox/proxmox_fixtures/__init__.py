"""Fixtures and helpers for Proxmox VE integration tests.

`real_path` is this directory; pass `f"{real_path}/<name>.json"` to `json_fixture` to load a JSON fixture.
"""

import os

from .nautobot_fixtures import (
    _get_device_interface_dict,
    _get_node_device_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
    create_default_proxmox_config,
)
from .sync_mixin import ProxmoxSyncTestMixin
from .utilities import json_fixture

__all__ = (
    "json_fixture",
    "create_default_proxmox_config",
    "ProxmoxSyncTestMixin",
    "_get_virtual_machine_dict",
    "_get_device_interface_dict",
    "_get_node_device_dict",
    "_get_vm_interface_dict",
)

real_path = os.path.dirname(os.path.realpath(__file__))
