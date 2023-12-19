"""Django Management command to update DCIM.Interface names."""
from django.core.management.base import BaseCommand

from nautobot.dcim.models import Device

from netutils.interface import canonical_interface_name as netutils_elongate_interface_name


class Command(BaseCommand):
    """MGMT command to use netutils to update Nautobot Interface names to use long format."""

    help = (
        "Elongate DCIM.Interface names in Nautobot based off of netutils: "
        "https://netutils.readthedocs.io/en/latest/dev/code_reference/interface/#netutils.interface.canonical_interface_name"
    )

    def add_arguments(self, parser):  # noqa: D102
        parser.add_argument(
            "-d",
            "--devices",
            default=None,
            help="DCIM.Device names to limit which devices have their interface names updated (comma separated).",
        )

        parser.add_argument(
            "-l",
            "--locations",
            default=None,
            help="DCIM.Location names to limit which devices have their interface names updated (comma separated).",
        )

    def handle(self, *args, **options):  # noqa: D102
        if options.get("devices"):
            device_option = [device.strip() for device in options["devices"].split(",")]
            devices = Device.objects.filter(name__in=device_option)
        elif options.get("locations"):
            device_option = [location.strip() for location in options["locations"].split(",")]
            devices = Device.objects.filter(location__name__in=device_option)
        else:
            devices = Device.objects.all()
        for device in devices:
            for interface in device.interfaces.all():
                new_name = netutils_elongate_interface_name(interface.name)
                if interface.name != new_name:
                    self.stdout.write(
                        self.style.WARNING(f"Updating {device.name}.{interface.name} >> ")
                        + self.style.SUCCESS(f"{new_name}")
                    )
                    interface.name = netutils_elongate_interface_name(new_name)
                    interface.validated_save()
