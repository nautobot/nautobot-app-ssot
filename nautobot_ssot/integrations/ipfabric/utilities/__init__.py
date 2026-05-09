"""Utilities."""

from .nbutils import (
    assign_device_to_virtual_chassis,
    create_interface,
    create_ip,
    create_vlan,
    get_or_create_device_role_object,
    get_or_create_device_type_object,
    get_or_create_location_object,
    get_or_create_manufacturer_object,
    get_or_create_platform_object,
    get_or_create_status_object,
    get_or_create_tag_object,
    get_or_create_virtual_chassis_object,
    get_tagged_device,
)
from .test_utils import clean_slate, json_fixture

__all__ = (
    "assign_device_to_virtual_chassis",
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
    "get_or_create_tag_object",
    "get_or_create_virtual_chassis_object",
    "get_tagged_device",
)
