"""Fixtures for Proxmox VE integration tests.

In your test file, simply import:
```
from .proxmox_fixtures import json_fixture, real_path
```
Then load a fixture you've added to this directory:

json_fixture(f"{real_path}/nodes.json")
"""

import os

from .nautobot_fixtures import (
    _get_device_interface_dict,
    _get_virtual_machine_dict,
    _get_vm_interface_dict,
    create_default_proxmox_config,
)
from .utilities import json_fixture

__all__ = (
    "json_fixture",
    "create_default_proxmox_config",
    "_get_virtual_machine_dict",
    "_get_device_interface_dict",
    "_get_vm_interface_dict",
)

real_path = os.path.dirname(os.path.realpath(__file__))
