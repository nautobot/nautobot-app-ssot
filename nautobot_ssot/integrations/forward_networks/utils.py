"""Utility functions for Forward Networks integration."""

import re
from typing import Dict, Optional

from nautobot.dcim.models import DeviceType, Manufacturer, Platform
from nautobot.extras.models import Status, Tag
from nautobot.ipam.models import Namespace


def normalize_device_name(name: str) -> str:
    """Normalize device name for consistency."""
    # Remove common prefixes/suffixes and normalize
    name = name.strip()
    # Replace spaces and special characters with hyphens
    name = re.sub(r"[^\w\-.]", "-", name)
    # Remove multiple consecutive hyphens
    name = re.sub(r"-+", "-", name)
    # Remove leading/trailing hyphens
    name = name.strip("-")
    return name


def normalize_interface_name(name: str) -> str:
    """Normalize interface name for consistency."""
    # Common interface name mappings
    mappings = {
        r"^Gi(\d+/\d+/\d+)$": r"GigabitEthernet\1",
        r"^Gi(\d+/\d+)$": r"GigabitEthernet\1",
        r"^Te(\d+/\d+/\d+)$": r"TenGigabitEthernet\1",
        r"^Te(\d+/\d+)$": r"TenGigabitEthernet\1",
        r"^Fo(\d+/\d+/\d+)$": r"FortyGigabitEthernet\1",
        r"^Fo(\d+/\d+)$": r"FortyGigabitEthernet\1",
        r"^Hu(\d+/\d+/\d+)$": r"HundredGigE\1",
        r"^Hu(\d+/\d+)$": r"HundredGigE\1",
    }

    name = name.strip()
    for pattern, replacement in mappings.items():
        name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

    return name


def get_or_create_manufacturer(name: str) -> Manufacturer:
    """Get or create manufacturer."""
    name = name.strip()
    if not name or name.lower() == "unknown":
        name = "Unknown"

    manufacturer, created = Manufacturer.objects.get_or_create(
        name=name, defaults={"description": "Manufacturer imported from Forward Networks"}
    )
    return manufacturer


def get_or_create_device_type(manufacturer: Manufacturer, model: str) -> DeviceType:
    """Get or create device type."""
    model = model.strip()
    if not model or model.lower() == "unknown":
        model = "Unknown"

    device_type, created = DeviceType.objects.get_or_create(
        model=model,
        manufacturer=manufacturer,
        defaults={
            "description": "Device type imported from Forward Networks",
            "u_height": 1,
        },
    )
    return device_type


def get_or_create_platform(name: str) -> Platform:
    """Get or create platform."""
    name = name.strip()
    if not name or name.lower() == "unknown":
        name = "Unknown"

    platform, created = Platform.objects.get_or_create(
        name=name, defaults={"description": "Platform imported from Forward Networks"}
    )
    return platform


def get_or_create_status(name: str = "Active") -> Status:
    """Get or create status."""
    status, created = Status.objects.get_or_create(
        name=name, defaults={"description": "Status for Forward Networks objects"}
    )
    return status


def get_or_create_tag(name: str) -> Tag:
    """Get or create tag."""
    tag, created = Tag.objects.get_or_create(name=name, defaults={"description": "Tag imported from Forward Networks"})
    return tag


def get_or_create_namespace(name: str = "Global") -> Namespace:
    """Get or create namespace."""
    namespace, created = Namespace.objects.get_or_create(
        name=name, defaults={"description": "Namespace for Forward Networks objects"}
    )
    return namespace


def parse_forward_networks_device_role(device_type: str, device_name: str) -> str:
    """Parse device role from Forward Networks device type and name."""
    device_type = device_type.lower() if device_type else ""
    device_name = device_name.lower() if device_name else ""

    # Common role mappings
    if any(term in device_type for term in ["firewall", "fw", "asa", "palo", "fortinet"]):
        return "firewall"
    elif any(term in device_type for term in ["router", "rtr", "asr", "isr"]):
        return "router"
    elif any(term in device_type for term in ["switch", "sw", "nexus", "catalyst"]):
        if any(term in device_name for term in ["core", "dist", "distribution"]):
            return "distribution"
        elif any(term in device_name for term in ["access", "acc"]):
            return "access"
        else:
            return "switch"
    elif any(term in device_type for term in ["lb", "balancer", "f5", "netscaler"]):
        return "load-balancer"
    elif any(term in device_type for term in ["wlc", "wireless", "wifi"]):
        return "wireless-controller"
    else:
        return "access"


def sanitize_custom_fields(custom_fields: Dict) -> Dict:
    """Sanitize custom fields for Nautobot compatibility."""
    if not custom_fields:
        return {}

    sanitized = {}
    for key, value in custom_fields.items():
        # Convert key to valid custom field name
        clean_key = re.sub(r"[^\w]", "_", key.lower())
        clean_key = clean_key.strip("_")

        # Ensure value is JSON serializable
        if isinstance(value, (str, int, float, bool, list, dict)):
            sanitized[clean_key] = value
        else:
            sanitized[clean_key] = str(value)

    return sanitized


def extract_ip_from_string(ip_string: str) -> Optional[str]:
    """Extract IP address from string that might contain CIDR notation."""
    if not ip_string:
        return None

    # Remove CIDR notation if present
    if "/" in ip_string:
        return ip_string.split("/")[0]

    return ip_string


def validate_mac_address(mac: str) -> Optional[str]:
    """Validate and normalize MAC address."""
    if not mac:
        return None

    # Remove common separators and normalize
    mac = re.sub(r"[:-]", "", mac.lower())

    # Check if it's a valid MAC address format
    if len(mac) == 12 and all(c in "0123456789abcdef" for c in mac):
        # Format as XX:XX:XX:XX:XX:XX
        return ":".join(mac[i : i + 2] for i in range(0, 12, 2))

    return None


def get_interface_type_from_name(interface_name: str) -> str:
    """Determine interface type from interface name."""
    name_lower = interface_name.lower()

    # Check more specific patterns first
    if any(term in name_lower for term in ["hundredgig", "hundred"]) or name_lower.startswith("hu"):
        return "100gbase-x-qsfp28"
    elif any(term in name_lower for term in ["fortygig", "forty"]) or name_lower.startswith("fo"):
        return "40gbase-x-qsfpp"
    elif any(term in name_lower for term in ["tengig", "tengigabit"]) or name_lower.startswith("te"):
        return "10gbase-x-sfpp"
    elif any(term in name_lower for term in ["gigabit"]) or name_lower.startswith("gi"):
        return "1000base-t"
    elif name_lower.startswith("eth") or name_lower.startswith("fa") or "fastethernet" in name_lower:
        return "100base-tx"
    elif any(term in name_lower for term in ["loopback", "lo"]):
        return "virtual"
    elif any(term in name_lower for term in ["vlan", "svi"]):
        return "virtual"
    elif any(term in name_lower for term in ["tunnel", "tun"]):
        return "virtual"
    elif any(term in name_lower for term in ["mgmt", "management"]):
        return "1000base-t"
    else:
        return "other"


def create_forward_networks_tag() -> Tag:
    """Create a tag to identify objects synced from Forward Networks."""
    tag, created = Tag.objects.get_or_create(
        name="SSoT Synced from Forward Networks",
        defaults={
            "description": "Objects synchronized from Forward Networks",
            "color": "2196f3",  # Blue color
        },
    )
    return tag
