"""Itential SsoT Nautobot device fixtures."""

from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import (
    Location,
    LocationType,
    Manufacturer,
    Platform,
    Device,
    DeviceType,
    Interface,
)
from nautobot.extras.models import Status, Role
from nautobot.ipam.models import Prefix, IPAddress, Namespace


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
    status: str,
    role: str,
    name: str,
    location: str,
    manufacturer: str,
    platform: str,
    network_driver: str,
    model: str,
    interface: str,
    ip_address: str,
    config_context: dict = {},
):  # pylint: disable=dangerous-default-value,too-many-arguments,too-many-locals
    """Create or update device fixtures."""
    status, _ = Status.objects.get_or_create(name=status)
    namespace, _ = Namespace.objects.get_or_create(name="Global")
    Prefix.objects.update_or_create(prefix="192.0.2.0/24", namespace=namespace, status=status)
    device_content_type = ContentType.objects.get_for_model(Device)
    role, role_changed = Role.objects.update_or_create(name=role)
    add_content_type(model=role, content_type=device_content_type, changed=role_changed)
    location_type, location_type_changed = LocationType.objects.get_or_create(name="Region")
    add_content_type(model=location_type, content_type=device_content_type, changed=location_type_changed)
    location, _ = Location.objects.get_or_create(name=location, location_type=location_type, status=status)
    manufacturer, _ = Manufacturer.objects.update_or_create(name=manufacturer)
    platform, _ = Platform.objects.update_or_create(
        name=platform, manufacturer=manufacturer, network_driver=network_driver
    )
    device_type, _ = DeviceType.objects.update_or_create(manufacturer=manufacturer, model=model)
    device, _ = Device.objects.update_or_create(
        name=name, role=role, device_type=device_type, location=location, status=status, platform=platform
    )
    interface, _ = Interface.objects.update_or_create(name=interface, status=status, device=device)

    if ip_address:
        ip_address, _ = IPAddress.objects.update_or_create(host=ip_address, mask_length=32, status=status)
        ip_address.primary_ip4_for.add(device)

    device.local_config_context_data = config_context
    device.save()
