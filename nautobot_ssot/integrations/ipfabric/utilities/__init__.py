"""Utilities."""

from .nbutils import (
    create_device_type_object,
    create_interface,
    create_ip,
    create_location,
    create_manufacturer,
    create_platform_object,
    create_status,
    create_vlan,
    get_or_create_device_role_object,
)
from .test_utils import clean_slate, json_fixture

__all__ = (
    "create_location",
    "create_device_type_object",
    "create_manufacturer",
    "create_platform_object",
    "get_or_create_device_role_object",
    "create_status",
    "create_ip",
    "create_interface",
    "json_fixture",
    "create_vlan",
    "clean_slate",
)
