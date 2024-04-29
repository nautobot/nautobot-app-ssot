"""Django Management command to update DCIM.Interface names."""

from django.core.management.base import BaseCommand

from nautobot.dcim.models import Device

from netutils.interface import canonical_interface_name


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

        parser.add_argument(
            "--cf_systems_of_record",
            default=None,
            help="Limits DCIM.Devices in scope to those that have a custom_field.system_of_record value to what is passed.",
        )

    def handle(self, *args, **options):  # noqa: D102
        device_limit = options.get("devices")
        location_limit = options.get("locations")
        if device_limit and location_limit:
            raise ValueError('Only one of "--devices" and "--locations" may be used.')

        if device_limit:
            device_option = [device.strip() for device in device_limit.split(",")]
            devices = Device.objects.filter(name__in=device_option)
        elif location_limit:
            device_option = [location.strip() for location in location_limit.split(",")]
            devices = Device.objects.filter(location__name__in=device_option)
        else:
            devices = Device.objects.all()

        cf_systems_of_record_limit = options.get("cf_systems_of_record")
        if cf_systems_of_record_limit:
            sor_option = [sor.strip() for sor in cf_systems_of_record_limit.split(",")]
            devices = devices.filter(_custom_field_data__system_of_record__in=sor_option)

        for device in devices:
            for interface in device.interfaces.all():
                new_name = canonical_interface_name(interface.name)
                if interface.name != new_name:
                    self.stdout.write(
                        self.style.WARNING(f"Updating {device.name}.{interface.name} >> ")
                        + self.style.SUCCESS(f"{new_name}")
                    )
                    interface.name = canonical_interface_name(new_name)
                    interface.validated_save()
