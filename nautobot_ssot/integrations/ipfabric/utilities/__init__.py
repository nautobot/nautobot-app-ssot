"""Utilities."""

from .nbutils import (
    create_interface,
    create_ip,
    create_vlan,
    get_or_create_device_role_object,
    get_or_create_device_type_object,
    get_or_create_location_object,
    get_or_create_manufacturer_object,
    get_or_create_platform_object,
    get_or_create_status_object,
)
from .test_utils import clean_slate, json_fixture

__all__ = (
    "create_ip",
    "create_interface",
    "json_fixture",
    "create_vlan",
    "clean_slate",
    "get_or_create_device_role_object",
    "get_or_create_device_type_object",
    "get_or_create_location_object",
    "get_or_create_manufacturer_object",
    "get_or_create_platform_object",
    "get_or_create_status_object",
)
