"""Tests for the writers every IP Fabric ORM helper writes through."""

from unittest import mock

from django.apps import apps as global_apps
from nautobot.dcim.models import Device, Interface, Location, VirtualChassis
from nautobot.ipam.models import VRF, VRFDeviceAssignment

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.writers import BatchedWriter, ImmediateWriter
from nautobot_ssot.tests.ipfabric.supporting_objects import (
    KNOWN_MODEL,
    KNOWN_PLATFORM,
    KNOWN_ROLE,
    KNOWN_VENDOR,
    SupportingObjectTestCase,
)


class WriterTestCase(SupportingObjectTestCase):
    """What each writer does with an object, and how a model's adapter picks one."""

    def setUp(self):
        super().setUp()
        nautobot_database_ready_callback(sender=None, apps=global_apps)
        self.pending = PendingWrites(mock.MagicMock())

    def new_location(self, name="new-site"):
        """Return an unsaved Location."""
        return Location(name=name, location_type=self.location.location_type, status=self.active_status)

    def synced(self, instance):
        """Return whether an object in the database carries the synced Tag and the stamp."""
        instance.refresh_from_db()
        tagged = instance.tags.filter(name=nbutils.SYNCED_TAG_NAME).exists()
        return tagged and instance.cf.get("system_of_record") == "IPFabric"

    def test_the_immediate_writer_saves_stamps_and_tags_a_new_object(self):
        writer = ImmediateWriter()
        location = writer.create(self.new_location())
        self.assertTrue(self.synced(location))
        self.assertIsNone(writer.find(Location, "new-site"))
        self.assertFalse(writer.holds(self.new_location("other")))

    def test_the_immediate_writer_saves_later_values_at_once(self):
        ImmediateWriter().set_later(self.location, {"description": "now"})
        self.location.refresh_from_db()
        self.assertEqual(self.location.description, "now")

    def test_the_batched_writer_queues_a_new_object_with_its_tag_row(self):
        writer = BatchedWriter(self.pending)
        location = writer.create(self.new_location(), key="new-site")
        self.assertFalse(Location.objects.filter(name="new-site").exists())
        self.assertIs(writer.find(Location, "new-site"), location)
        self.assertTrue(writer.holds(location))
        self.pending.flush()
        self.assertTrue(self.synced(location))

    def test_the_batched_writer_saves_an_object_already_written_and_not_a_queued_one(self):
        writer = BatchedWriter(self.pending)
        self.location.description = "saved"
        writer.save(self.location)
        self.location.refresh_from_db()
        self.assertEqual(self.location.description, "saved")
        queued = writer.create(self.new_location(), key="new-site")
        writer.save(queued)
        self.assertFalse(Location.objects.filter(name="new-site").exists())

    def test_the_batched_writer_defers_later_values_until_the_flush(self):
        writer = BatchedWriter(self.pending)
        writer.set_later(self.location, {"description": "later"})
        self.location.refresh_from_db()
        self.assertEqual(self.location.description, "")
        self.pending.flush()
        self.location.refresh_from_db()
        self.assertEqual(self.location.description, "later")

    def test_an_adapter_writes_through_a_queue_only_when_given_one(self):
        adapter = DiffSyncModelAdapters()
        self.assertIsInstance(adapter.writer, ImmediateWriter)
        self.assertIsNone(adapter.pending)
        adapter.pending = self.pending
        self.assertIsInstance(adapter.writer, BatchedWriter)
        self.assertIs(adapter.pending, self.pending)
        adapter.pending = None
        self.assertIsInstance(adapter.writer, ImmediateWriter)


class BatchedWritesToObjectsAlreadyWrittenTestCase(SupportingObjectTestCase):
    """In Bulk Write Mode, a change to an object Nautobot already holds is still written."""

    def setUp(self):
        super().setUp()
        nautobot_database_ready_callback(sender=None, apps=global_apps)
        self.create_device(name="member")
        self.device = Device.objects.get(name="member")
        self.writer = BatchedWriter(PendingWrites(mock.MagicMock()))

    def test_an_existing_devices_virtual_chassis_membership_is_saved(self):
        stack = VirtualChassis.objects.create(name="stack")
        nbutils.assign_device_to_virtual_chassis(self.device, stack, position=2, priority=2, writer=self.writer)
        self.device.refresh_from_db()
        self.assertEqual((self.device.virtual_chassis, self.device.vc_position), (stack, 2))

    def test_a_device_moved_to_a_location_this_run_queued_is_moved_once_it_is_written(self):
        self.adapter.pending = PendingWrites(mock.MagicMock())
        model = DeviceModel(
            adapter=self.adapter,
            name="member",
            location_name=self.location.name,
            model=KNOWN_MODEL,
            vendor=KNOWN_VENDOR,
            role=KNOWN_ROLE,
            status="Active",
            platform=KNOWN_PLATFORM,
            serial_number="abc123",
        )
        model.update({"location_name": "queued-site"})
        self.device.refresh_from_db()
        self.assertEqual(self.device.location, self.location, "Saved pointing at a row that is not written yet.")
        self.adapter.pending.flush()
        self.device.refresh_from_db()
        self.assertEqual(self.device.location.name, "queued-site")

    def queued_port_channel(self):
        """Queue a port channel on the Device, as an Interface created earlier in a bulk run."""
        return self.writer.create(
            Interface(device=self.device, name="Port-Channel1", type="lag", status=self.active_status),
            key=(self.device.pk, "Port-Channel1"),
        )

    def test_an_existing_interface_joins_a_port_channel_this_run_queued_once_it_is_written(self):
        member = Interface.objects.create(device=self.device, name="eth0", type="1000base-t", status=self.active_status)
        self.adapter.pending = self.writer.pending
        port_channel = self.queued_port_channel()
        InterfaceModel(adapter=self.adapter, name="eth0", device_name="member", status="Active").update(
            {"lag": "Port-Channel1"}
        )
        member.refresh_from_db()
        self.assertIsNone(member.lag)
        self.writer.pending.flush()
        member.refresh_from_db()
        self.assertEqual(member.lag, port_channel)

    def test_a_queued_interface_carries_its_vrf_into_its_insert(self):
        vrf = VRF.objects.create(name="BLUE", status=self.active_status)
        VRFDeviceAssignment.objects.create(vrf=vrf, device=self.device, rd=vrf.rd, name=vrf.name)
        port_channel = self.queued_port_channel()
        self.assertTrue(
            nbutils.set_interface_vrf(
                "member", "Port-Channel1", "BLUE", scope=nbutils.DeviceScope(), writer=self.writer
            )
        )
        self.assertEqual(port_channel.vrf, vrf)
        self.assertFalse(Interface.objects.filter(name="Port-Channel1").exists())
