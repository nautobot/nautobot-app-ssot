"""Add the basic data needed on the Nautobot side via the ORM."""

from django.core.management.base import BaseCommand

from nautobot.dcim.models import Site, DeviceRole, DeviceType, Manufacturer, Device, Interface, Platform
from nautobot.ipam.models import IPAddress
from nautobot.extras.models.statuses import Status

devices_data = [
    {
        "slug": "ams01-edge-01",
        "interface": {
            "name": "vlan101",
            "device": "ams01-edge-01",
            "description": "",
            "mode": "access",
            "active": True,
            "type": "10gbase-t",
            "status": "active",
            "ip_addresses": {
                "device": "ams01-edge-01",
                "interface": "vlan101",
                "address": "10.100.1.1/24",
                "status": "active",
            },
        },
    },
    {
        "slug": "ams01-edge-02",
        "interface": {
            "name": "vlan102",
            "device": "ams01-edge-02",
            "description": "",
            "mode": "access",
            "active": True,
            "type": "10gbase-t",
            "status": "active",
            "ip_addresses": {
                "device": "ams01-edge-02",
                "interface": "vlan102",
                "address": "10.100.2.1/24",
                "status": "active",
            },
        },
    },
    {
        "slug": "ams01-edge-03",
        "interface": {
            "name": "vlan103",
            "device": "ams01-edge-03",
            "description": "",
            "mode": "access",
            "active": True,
            "type": "10gbase-t",
            "status": "active",
            "ip_addresses": {
                "device": "ams01-edge-03",
                "interface": "vlan103",
                "address": "10.100.3.1/24",
                "status": "active",
            },
        },
    },
]


class Command(BaseCommand):
    """Publish command to data needed on the Nautobot side via the ORM."""

    help = "Create minimal amount of data on fresh instance to allow job to sync with network importer."

    def handle(self, *args, **kwargs):
        """Add handler for `dev_init_data`."""
        site_obj = Site.objects.create(name="ams01", slug="ams01")
        site_obj.save()

        manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
        device_role = DeviceRole.objects.create(name="Switch", slug="switch")
        device_type = DeviceType.objects.create(slug="C9410R", model="C9410R", manufacturer=manufacturer)
        platform = Platform.objects.create(name="ios", slug="ios")
        status = Status.objects.get(slug="active")

        for value in devices_data:
            device_obj = Device.objects.create(
                platform=platform,
                device_role=device_role,
                device_type=device_type,
                site=site_obj,
                name=value["slug"],
                status=status,
            )
            device_obj.save()

            ip_obj = IPAddress.objects.create(
                address=value["interface"]["ip_addresses"]["address"],
                status=status,
            )
            ip_obj.validated_save()

            int_obj = Interface.objects.create(
                device=device_obj,
                status=status,
                name=value["interface"]["name"],
                description=value["interface"]["description"],
                type=value["interface"]["type"],
                mode=value["interface"]["mode"],
            )
            int_obj.ip_addresses.add(ip_obj)
            int_obj.validated_save()
            device_obj.primary_ip4 = ip_obj
            device_obj.validated_save()
