"""Arista CloudVision Type Definitions."""

from typing import NamedTuple


class CloudVisionAppConfig(NamedTuple):
    """Arista CloudVision Configuration."""

    is_on_premise: bool
    url: str
    verify_ssl: bool
    cvp_user: str
    cvp_password: str
    token: str
    delete_devices_on_sync: bool
    from_cloudvision_default_site: str
    from_cloudvision_default_device_role: str
    from_cloudvision_default_device_role_color: str
    apply_import_tag: bool
    import_active: bool
    hostname_patterns: list
    site_mappings: dict
    role_mappings: dict
    controller_site: str
    create_controller: bool
