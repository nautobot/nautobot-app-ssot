"""Itential SsoT Nautobot device fixtures."""

from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix

data = [
    {
        "name": "rtr1.example.net",
        "location": "North America",
        "manufacturer": "Cisco",
        "model": "Cisco 2901",
        "interface": "gigabitEthernet0/1",
        "ip_address": "192.0.2.1",
        "platform": "Cisco IOS",
        "network_driver": "cisco_ios",
        "role": "Router",
        "status": "Active",
        "config_context": {"ansible_port": 22, "ansible_connection": "ansible.netcommon.network_cli"},
    },
    {
        "name": "rtr2.example.net",
        "location": "North America",
        "manufacturer": "Cisco",
        "model": "Cisco 2901",
        "interface": "gigabitEthernet0/1",
        "ip_address": None,
        "platform": "Cisco IOS",
        "network_driver": "cisco_ios",
        "role": "Router",
        "status": "Active",
    },
    {
        "name": "rtr10.example.net",
        "location": "North America",
        "manufacturer": "Cisco",
        "model": "Cisco 2901",
        "interface": "gigabitEthernet0/1",
        "ip_address": "192.0.2.10",
        "platform": "Cisco IOS",
        "network_driver": "cisco_ios",
        "role": "Router",
        "status": "Active",
    },
    {
        "name": "rtr11.example.net",
        "location": "North America",
        "manufacturer": "Cisco",
        "model": "NCS 5501",
        "interface": "managementEthernet0/0/0/1",
        "ip_address": "192.0.2.11",
        "platform": "Cisco IOS-XR",
        "network_driver": "cisco_xr",
        "role": "Router",
        "status": "Active",
    },
]


def add_content_type(model: object, content_type: object, changed: bool):
    """Add a content type to a model."""

    if changed:
        model.content_types.add(content_type)

    model.save()


def update_or_create_device_object(
    status_name: str,
    role_name: str,
    name: str,
    location_name: str,
    manufacturer_name: str,
    platform_name: str,
    network_driver: str,
    model: str,
    interface_name: str,
    ip_host: str,
    config_context: dict = {},
):  # pylint: disable=dangerous-default-value,too-many-arguments,too-many-locals
    """Create or update device fixtures."""
    status, _ = Status.objects.get_or_create(name=status_name)
    namespace, _ = Namespace.objects.get_or_create(name="Global")
    Prefix.objects.update_or_create(prefix="192.0.2.0/24", namespace=namespace, status=status)
    device_content_type = ContentType.objects.get_for_model(Device)
    role, role_changed = Role.objects.update_or_create(name=role_name)
    add_content_type(model=role, content_type=device_content_type, changed=role_changed)
    location_type, location_type_changed = LocationType.objects.get_or_create(name="Region")
    add_content_type(model=location_type, content_type=device_content_type, changed=location_type_changed)
    location, _ = Location.objects.get_or_create(name=location_name, location_type=location_type, status=status)
    manufacturer, _ = Manufacturer.objects.update_or_create(name=manufacturer_name)
    platform, _ = Platform.objects.update_or_create(
        name=platform_name, manufacturer=manufacturer, network_driver=network_driver
    )
    device_type, _ = DeviceType.objects.update_or_create(manufacturer=manufacturer, model=model)
    device, _ = Device.objects.update_or_create(
        name=name, role=role, device_type=device_type, location=location, status=status, platform=platform
    )
    Interface.objects.update_or_create(name=interface_name, status=status, device=device)

    if ip_host:
        ip_address, _ = IPAddress.objects.get_or_create(host=ip_host, defaults={"mask_length": 32, "status": status})
        ip_address.primary_ip4_for.add(device)

    device.local_config_context_data = config_context
    device.save()
