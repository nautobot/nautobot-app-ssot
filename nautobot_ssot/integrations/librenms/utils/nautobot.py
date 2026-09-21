"""Utility functions for working with Nautobot."""

# pylint: disable=duplicate-code

from functools import lru_cache
from uuid import UUID

from nautobot.dcim.models import Platform
from nautobot.dcim.utils import get_all_network_driver_mappings
from netutils.lib_mapper import (
    ANSIBLE_LIB_MAPPER,
    ANSIBLE_LIB_MAPPER_REVERSE,
    MAIN_LIB_MAPPER,
    NAPALM_LIB_MAPPER_REVERSE,
)

from nautobot_ssot.integrations.librenms.constants import (
    LIBRENMS_OS_TO_NETWORK_DRIVER,
    PLUGIN_CFG,
)


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


@lru_cache(maxsize=1)
def known_network_drivers() -> frozenset:
    """Network drivers this install recognizes."""
    # get_all_network_driver_mappings() honors the operator's NETWORK_DRIVERS setting.
    # MAIN_LIB_MAPPER recovers f5_tmsh, f5_ltm, f5_linux, ruckus_smartzone, absent from it.
    return frozenset(get_all_network_driver_mappings()) | frozenset(MAIN_LIB_MAPPER)


@lru_cache(maxsize=None)
def librenms_os_to_network_driver(librenms_os: str) -> str:
    """Resolve a LibreNMS `os` to a network driver, or "" when unknown."""
    if not librenms_os:
        return ""
    key = str(librenms_os).strip().lower()
    if not key:
        return ""

    # Setting wins; explicit "" suppresses a bundled mapping.
    overrides = PLUGIN_CFG.get("librenms_network_driver_map") or {}
    for override_os, override_driver in overrides.items():
        if str(override_os).strip().lower() == key:
            return str(override_driver).strip() if override_driver else ""

    if key in LIBRENMS_OS_TO_NETWORK_DRIVER:
        return LIBRENMS_OS_TO_NETWORK_DRIVER[key]

    if key in known_network_drivers():
        return key

    # Never invent a driver.
    return ""


def platform_to_network_driver(platform) -> str:
    """Canonical driver-space key for an existing Platform. Consolidated mode only."""
    # Understands legacy shapes so enabling the flag produces no diff for existing platforms.
    if platform is None:
        return ""

    # Covers onboarding (cisco_ios/cisco_ios) and dna_center (cisco.ios.ios/cisco_ios).
    driver = (platform.network_driver or "").strip()
    if driver and driver in known_network_drivers():
        return driver

    # FQCN -> driver is unambiguous, unlike the reverse that caused the original bug.
    name = (platform.name or "").strip()
    for candidate in (driver, name):
        if candidate and candidate in ANSIBLE_LIB_MAPPER:
            return ANSIBLE_LIB_MAPPER[candidate]

    # Legacy rows named after the raw OS.
    resolved = librenms_os_to_network_driver(name)
    if resolved:
        return resolved

    # Hand-made platforms keep their identity.
    return driver or name


def clear_network_driver_caches() -> None:
    """Drop cached driver lookups so settings changes apply per sync, not per worker restart."""
    known_network_drivers.cache_clear()
    librenms_os_to_network_driver.cache_clear()
