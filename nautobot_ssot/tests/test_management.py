"""Test cases for custom Django MGMT commands."""

from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase

from nautobot.dcim.models import (
    Device,
    DeviceType,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.models import CustomField, Role, Status


class TestElongateInterfaceNames(TestCase):
    """Unittests for elongate_interface_names command."""

    def setUp(self):  # pylint: disable=too-many-locals
        """Per-test setup."""
        ct_device = ContentType.objects.get_for_model(Device)
        active_status = Status.objects.get(name="Active")

        cf_sor = CustomField.objects.create(label="system_of_record", type="text")
        cf_sor.content_types.add(ct_device)

        role = Role.objects.create(name="ssot_test")
        role.content_types.add(ct_device)

        location_type = LocationType.objects.create(name="ssot_test")
        location_type.content_types.add(ct_device)
        location_1 = Location.objects.create(name="ssot_test_1", status=active_status, location_type=location_type)
        location_2 = Location.objects.create(name="ssot_test_2", status=active_status, location_type=location_type)
        location_3 = Location.objects.create(name="ssot_test_3", status=active_status, location_type=location_type)

        manufacturer = Manufacturer.objects.create(name="ssot_test")
        platform = Platform.objects.create(name="ssot_test", manufacturer=manufacturer)
        device_type = DeviceType.objects.create(model="ssot_test", manufacturer=manufacturer)
        device1 = Device.objects.create(
            name="ssot_test_1",
            status=active_status,
            location=location_1,
            platform=platform,
            role=role,
            device_type=device_type,
            _custom_field_data={"system_of_record": "ipfabric"},
        )
        device2 = Device.objects.create(
            name="ssot_test_2",
            status=active_status,
            location=location_1,
            platform=platform,
            role=role,
            device_type=device_type,
            _custom_field_data={"system_of_record": "servicenow"},
        )
        device3 = Device.objects.create(
            name="ssot_test_3",
            status=active_status,
            location=location_2,
            platform=platform,
            role=role,
            device_type=device_type,
        )
        device4 = Device.objects.create(
            name="ssot_test_4",
            status=active_status,
            location=location_3,
            platform=platform,
            role=role,
            device_type=device_type,
        )

        device1.interfaces.create(name="GigabitEthernet1", status=active_status, type="1000base-t")
        device1.interfaces.create(name="ge2", status=active_status, type="1000base-t")
        device1.interfaces.create(name="skipme", status=active_status, type="1000base-t")

        device2.interfaces.create(name="ge2", status=active_status, type="1000base-t")
        device3.interfaces.create(name="ge2", status=active_status, type="1000base-t")
        device4.interfaces.create(name="ge1", status=active_status, type="1000base-t")
        device4.interfaces.create(name="ge2", status=active_status, type="1000base-t")
        return super().setUp()

    def test_pass_arg_devices_single(self):
        out = StringIO()
        call_command("elongate_interface_names", "--no-color", "--skip-checks", devices="ssot_test_1", stdout=out)
        self.assertEqual(out.getvalue().strip(), "Updating ssot_test_1.ge2 >> GigabitEthernet2")

    def test_pass_arg_devices_single_multiple_interfaces(self):
        out = StringIO()
        call_command("elongate_interface_names", "--no-color", "--skip-checks", devices="ssot_test_4", stdout=out)
        self.assertEqual(
            out.getvalue().strip(),
            "Updating ssot_test_4.ge1 >> GigabitEthernet1\nUpdating ssot_test_4.ge2 >> GigabitEthernet2",
        )

    def test_pass_arg_devices_multiple(self):
        out = StringIO()
        call_command(
            "elongate_interface_names", "--no-color", "--skip-checks", devices="ssot_test_1, ssot_test_2", stdout=out
        )
        self.assertEqual(
            out.getvalue().strip(),
            "Updating ssot_test_1.ge2 >> GigabitEthernet2\nUpdating ssot_test_2.ge2 >> GigabitEthernet2",
        )

    def test_pass_arg_locations_single(self):
        out = StringIO()
        call_command("elongate_interface_names", "--no-color", "--skip-checks", locations="ssot_test_1", stdout=out)
        self.assertEqual(
            out.getvalue().strip(),
            "Updating ssot_test_1.ge2 >> GigabitEthernet2\nUpdating ssot_test_2.ge2 >> GigabitEthernet2",
        )

    def test_pass_arg_locations_multiple(self):
        out = StringIO()
        call_command(
            "elongate_interface_names", "--no-color", "--skip-checks", locations="ssot_test_1, ssot_test_2", stdout=out
        )
        self.assertEqual(
            out.getvalue().strip(),
            (
                "Updating ssot_test_1.ge2 >> GigabitEthernet2\n"
                "Updating ssot_test_2.ge2 >> GigabitEthernet2\n"
                "Updating ssot_test_3.ge2 >> GigabitEthernet2"
            ),
        )

    def test_pass_no_args(self):
        out = StringIO()
        call_command("elongate_interface_names", "--no-color", "--skip-checks", stdout=out)
        self.assertEqual(
            out.getvalue().strip(),
            (
                "Updating ssot_test_1.ge2 >> GigabitEthernet2\n"
                "Updating ssot_test_2.ge2 >> GigabitEthernet2\n"
                "Updating ssot_test_3.ge2 >> GigabitEthernet2\n"
                "Updating ssot_test_4.ge1 >> GigabitEthernet1\n"
                "Updating ssot_test_4.ge2 >> GigabitEthernet2"
            ),
        )

    def test_pass_devices_and_locations_arg(self):
        out = StringIO()
        with self.assertRaises(ValueError, msg='Only one of "--devices" and "--locations" may be used.'):
            call_command(
                "elongate_interface_names",
                "--no-color",
                "--skip-checks",
                devices="ssot_test_1",
                locations="ssot_test_1",
                stdout=out,
            )

    def test_pass_cf_sor_arg_single(self):
        out = StringIO()
        call_command(
            "elongate_interface_names", "--no-color", "--skip-checks", cf_systems_of_record="ipfabric", stdout=out
        )
        self.assertEqual(out.getvalue().strip(), "Updating ssot_test_1.ge2 >> GigabitEthernet2")

    def test_pass_cf_sor_arg_multiple(self):
        out = StringIO()
        call_command(
            "elongate_interface_names",
            "--no-color",
            "--skip-checks",
            cf_systems_of_record="ipfabric,servicenow",
            stdout=out,
        )
        self.assertEqual(
            out.getvalue().strip(),
            "Updating ssot_test_1.ge2 >> GigabitEthernet2\nUpdating ssot_test_2.ge2 >> GigabitEthernet2",
        )

    def test_pass_location_and_cf_sor_args(self):
        out = StringIO()
        call_command(
            "elongate_interface_names",
            "--no-color",
            "--skip-checks",
            locations="ssot_test_1,ssot_test_3",
            cf_systems_of_record="ipfabric",
            stdout=out,
        )
        self.assertEqual(out.getvalue().strip(), "Updating ssot_test_1.ge2 >> GigabitEthernet2")
