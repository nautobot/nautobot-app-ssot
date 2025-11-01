"""Utility functions for working with Nautobot."""

from uuid import UUID

from nautobot.dcim.models import Platform
from netutils.lib_mapper import ANSIBLE_LIB_MAPPER_REVERSE, NAPALM_LIB_MAPPER_REVERSE


def verify_platform(platform_name: str, manu: UUID) -> Platform:
    """Verifies Platform object exists in Nautobot. If not, creates it.

    Args:
        platform_name (str): Name of platform to verify.
        manu (UUID): The ID (primary key) of platform manufacturer.

    Returns:
        Platform: Found or created Platform object.
    """
    if ANSIBLE_LIB_MAPPER_REVERSE.get(platform_name):
        _name = ANSIBLE_LIB_MAPPER_REVERSE[platform_name]
    else:
        _name = platform_name
    if NAPALM_LIB_MAPPER_REVERSE.get(platform_name):
        napalm_driver = NAPALM_LIB_MAPPER_REVERSE[platform_name]
    else:
        napalm_driver = platform_name
    try:
        platform_obj = Platform.objects.get(network_driver=platform_name)
    except Platform.DoesNotExist:
        platform_obj = Platform(
            name=_name, manufacturer_id=manu, napalm_driver=napalm_driver[:50], network_driver=platform_name
        )
        platform_obj.validated_save()
    return platform_obj
