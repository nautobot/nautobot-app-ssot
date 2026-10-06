"""Tests for which of IP Fabric's two serial numbers reaches which Nautobot field.

IP Fabric reports `sn`, the serial it identifies a Device by, and `snHw`, the serial on the chassis.
Nautobot's `Device.serial` means the chassis one, so that is what it gets; the key IP Fabric matched
on is recorded beside it rather than written over it.
"""

from collections import defaultdict

from ipfabric.models.device import Device as IPFabricDevice
from nautobot.apps.testing import TestCase
from nautobot.core.models.fields import CHARFIELD_MAX_LENGTH
from nautobot.dcim.models import Device as NautobotDevice

from nautobot_ssot.integrations.ipfabric.constants import DEVICE_UNIQUE_SERIAL_CF_NAME
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import holdable_serial
from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.supporting_objects import SupportingObjectTestCase
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import (
    DEVICE_INVENTORY_FIXTURE,
    build_adapter,
    mock_ipfabric_client,
)


class TestAServialNautobotCanHold(TestCase):
    """What counts as a chassis serial worth recording."""

    def test_a_serial_within_the_field_is_held(self):
        self.assertEqual("ABC123", holdable_serial("ABC123"))

    def test_a_serial_of_exactly_the_field_length_is_held(self):
        """The boundary: a serial the field fits exactly is a serial, not an overflow."""
        serial = "s" * CHARFIELD_MAX_LENGTH

        self.assertEqual(serial, holdable_serial(serial))

    def test_a_serial_one_longer_than_the_field_is_refused(self):
        """Refused rather than truncated: a prefix of a serial names no chassis."""
        self.assertIsNone(holdable_serial("s" * (CHARFIELD_MAX_LENGTH + 1)))

    def test_nothing_reported_is_an_absence_not_an_empty_serial(self):
        """`None` and `""` mean different things to the diff, so this must not return `""`."""
        for reported in (None, "", "   "):
            with self.subTest(reported=reported):
                self.assertIsNone(holdable_serial(reported))


class TestWhichSerialIsLoaded(TestCase):
    """What the IP Fabric adapter reports for a Device's two serials."""

    def loaded(self, **overrides):
        """Return `(devices keyed by name, the adapter, the job's logger)` over the fixtures."""
        client = mock_ipfabric_client()
        client.devices.by_site = defaultdict(list)
        for record in DEVICE_INVENTORY_FIXTURE:
            record = dict(record, **overrides)
            client.devices.by_site[record["siteName"]].append(IPFabricDevice(**record))  # pylint: disable=no-member
        logger = job_logger()
        adapter = build_adapter(client=client, logger=logger)
        devices = {device.name: device for device in adapter.get_all("device")}
        return devices, adapter, logger

    def test_the_chassis_serial_is_what_reaches_the_serial_field(self):
        """`snHw` rather than `sn`: Nautobot documents the field as the chassis serial."""
        devices, _, _ = self.loaded(snHw="CHASSIS-1")

        self.assertEqual("CHASSIS-1", devices["nyc-rtr-01"].serial_number)

    def test_the_serial_ip_fabric_keys_on_is_recorded_beside_it(self):
        """Not lost: it is the key a run matched the Device on, so it stays visible."""
        devices, _, _ = self.loaded(snHw="CHASSIS-1")

        self.assertEqual("VM60D5EE2211", devices["nyc-rtr-01"].unique_serial)

    def test_a_device_with_no_chassis_serial_reports_none_rather_than_an_empty_one(self):
        """A virtual Device has no chassis, so there is nothing to report rather than nothing to be.

        An empty string would be a value, and would drive the serial Nautobot holds to empty on
        every run. `None` is an absence, which the Nautobot side reports too.
        """
        devices, adapter, logger = self.loaded()

        self.assertIsNone(devices["nyc-rtr-01"].serial_number)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_hardware_serial)
        self.assertIn("reports no chassis serial for", job_log_text(logger, "warning"))

    def test_the_unique_serial_is_recorded_even_with_no_chassis_serial(self):
        """The two are independent: one being absent must not withhold the other."""
        devices, _, _ = self.loaded()

        self.assertEqual("VM60D5EE2211", devices["nyc-rtr-01"].unique_serial)

    def test_a_chassis_serial_too_long_to_hold_is_reported_as_absent(self):
        """Same treatment as none reported, since neither can be written."""
        devices, adapter, _ = self.loaded(snHw="s" * (CHARFIELD_MAX_LENGTH + 1))

        self.assertIsNone(devices["nyc-rtr-01"].serial_number)
        self.assertIn("nyc-rtr-01", adapter.devices_without_a_hardware_serial)


class TestWritingTheSerials(SupportingObjectTestCase):
    """What reaches Nautobot when the sync creates a Device."""

    def written(self, name="dev1", **overrides):
        """Create a Device through the sync's own model and return the Nautobot record."""
        self.create_device(name=name, **overrides)
        return NautobotDevice.objects.filter(name=name).first()

    def test_the_chassis_serial_is_written_to_the_serial_field(self):
        device = self.written(serial_number="CHASSIS-1", unique_serial="KEY-1")

        self.assertIsNotNone(device, "The Device must be created.")
        self.assertEqual("CHASSIS-1", device.serial)

    def test_the_unique_serial_is_written_to_its_custom_field(self):
        device = self.written(serial_number="CHASSIS-1", unique_serial="KEY-1")

        self.assertEqual("KEY-1", device.cf[DEVICE_UNIQUE_SERIAL_CF_NAME])

    def test_a_device_with_no_chassis_serial_is_still_created(self):
        """`Device.serial` is not nullable, so reporting none must not become a null write."""
        device = self.written(serial_number=None, unique_serial="KEY-1")

        self.assertIsNotNone(device, "Reporting no serial must not stop the Device being written.")
        self.assertEqual("", device.serial, "A new Device has no earlier serial to keep.")
        self.assertEqual("KEY-1", device.cf[DEVICE_UNIQUE_SERIAL_CF_NAME])
