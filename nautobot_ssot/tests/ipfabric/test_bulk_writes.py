"""Tests for the batched write collector used by bulk write mode.

These write against the real database, since what is being tested is whether a batched insert built
this way produces the same rows a per-object save would.
"""

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status, Tag, TaggedItem
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot.ipam.models import (
    VLAN,
    IPAddress,
    IPAddressToInterface,
    Prefix,
    VLANLocationAssignment,
    get_default_namespace,
)

from nautobot_ssot.integrations.ipfabric.bulk_writes import LEVELS, PendingWrites


class PendingWritesTestCase(TestCase):
    """Test queueing and flushing."""

    def setUp(self):
        populate_status_choices()
        self.active = Status.objects.get(name="Active")
        self.namespace = get_default_namespace()
        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            namespace=self.namespace,
            defaults={"status": self.active, "type": PrefixTypeChoices.TYPE_NETWORK},
        )
        device_ct = ContentType.objects.get_for_model(Device)
        self.role = Role.objects.create(name="bulk-role")
        self.role.content_types.add(device_ct)
        self.location_type, _ = LocationType.objects.get_or_create(name="bulk-site")
        self.location_type.content_types.add(device_ct, ContentType.objects.get_for_model(VLAN))
        manufacturer = Manufacturer.objects.create(name="bulk-vendor")
        self.device_type = DeviceType.objects.create(model="bulk-model", manufacturer=manufacturer)
        self.tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        self.tag.content_types.add(device_ct, ContentType.objects.get_for_model(Interface))
        self.pending = PendingWrites()

    def build_location(self, name):
        """Return an unsaved Location, primary key already assigned."""
        return Location(name=name, location_type=self.location_type, status=self.active)

    def build_device(self, name, location):
        """Return an unsaved Device referencing a Location that may itself be unsaved."""
        return Device(
            name=name,
            status=self.active,
            role=self.role,
            location_id=location.pk,
            device_type=self.device_type,
            serial="serial",
        )

    def build_interface(self, name, device):
        """Return an unsaved Interface referencing a Device that may itself be unsaved."""
        return Interface(device_id=device.pk, name=name, status=self.active, type="1000base-t")

    # --- ordering ---

    def test_a_child_written_with_its_parent_in_the_same_flush(self):
        """The whole point: a child may reference a parent that has not been written yet."""
        location = self.pending.add(self.build_location("child-order"))
        device = self.pending.add(self.build_device("child-order-device", location))
        interface = self.pending.add(self.build_interface("eth0", device))

        self.pending.flush()

        written = Interface.objects.get(pk=interface.pk)
        self.assertEqual(written.device.name, "child-order-device")
        self.assertEqual(written.device.location.name, "child-order")

    def test_levels_are_ordered_so_a_parent_precedes_its_children(self):
        """A reordering here would insert children before the rows they point at."""
        self.assertLess(LEVELS.index(Location), LEVELS.index(Device))
        self.assertLess(LEVELS.index(Device), LEVELS.index(Interface))
        self.assertLess(LEVELS.index(Location), LEVELS.index(VLAN))

    # --- finding a queued parent ---

    def test_a_queued_object_can_be_found_by_key(self):
        location = self.pending.add(self.build_location("findable"), key="findable")
        self.assertIs(self.pending.find(Location, "findable"), location)

    def test_finding_something_never_queued_returns_none(self):
        self.assertIsNone(self.pending.find(Location, "absent"))

    def test_keys_are_forgotten_once_written(self):
        """A flushed object is in the database, so the next lookup should go there instead."""
        self.pending.add(self.build_location("forgotten"), key="forgotten")
        self.pending.flush()
        self.assertIsNone(self.pending.find(Location, "forgotten"))

    def test_an_unsupported_model_is_refused(self):
        with self.assertRaises(ValueError):
            self.pending.add(Prefix(prefix="10.1.0.0/16", namespace=self.namespace, status=self.active))

    # --- join tables ---

    def test_join_rows_are_written_after_what_they_reference(self):
        location = self.pending.add(self.build_location("join"))
        device = self.pending.add(self.build_device("join-device", location))
        interface = self.pending.add(self.build_interface("eth0", device))
        self.pending.add_through(
            TaggedItem(
                content_type=ContentType.objects.get_for_model(Interface),
                object_id=interface.pk,
                tag=self.tag,
            )
        )

        self.pending.flush()

        self.assertTrue(Interface.objects.get(pk=interface.pk).tags.filter(pk=self.tag.pk).exists())

    def test_an_address_is_assigned_to_an_interface_in_one_flush(self):
        location = self.pending.add(self.build_location("addr"))
        device = self.pending.add(self.build_device("addr-device", location))
        interface = self.pending.add(self.build_interface("eth0", device))
        address = IPAddress(address="10.0.0.1/24", namespace=self.namespace, status=self.active)
        # `IPAddress.save()` resolves this; a batched insert has to be handed it.
        address.parent = address._get_closest_parent()  # pylint: disable=protected-access
        self.pending.add(address)
        self.pending.add_through(IPAddressToInterface(ip_address=address, interface_id=interface.pk))

        self.pending.flush()

        written = Interface.objects.get(pk=interface.pk)
        self.assertEqual([str(each.host) for each in written.ip_addresses.all()], ["10.0.0.1"])
        self.assertEqual(
            IPAddress.objects.get(pk=address.pk).parent.prefix, Prefix.objects.get(prefix="10.0.0.0/8").prefix
        )

    def test_a_vlan_gets_its_location_assignment(self):
        """`VLAN.save()` makes this assignment, so a batched insert has to make it instead."""
        location = self.pending.add(self.build_location("vlan-site"))
        vlan = self.pending.add(VLAN(vid=10, name="bulk-vlan", status=self.active))
        self.pending.add_through(VLANLocationAssignment(vlan=vlan, location_id=location.pk))

        self.pending.flush()

        self.assertEqual([each.name for each in VLAN.objects.get(pk=vlan.pk).locations.all()], ["vlan-site"])

    def test_an_unsupported_join_table_is_refused(self):
        with self.assertRaises(ValueError):
            self.pending.add_through(Prefix(prefix="10.2.0.0/16", namespace=self.namespace, status=self.active))

    # --- deferred updates ---

    def test_a_deferred_update_is_applied_after_insertion(self):
        """A Device's primary IP is only knowable once the address exists."""
        location = self.pending.add(self.build_location("primary"))
        device = self.pending.add(self.build_device("primary-device", location))
        interface = self.pending.add(self.build_interface("eth0", device))
        address = IPAddress(address="10.0.0.5/24", namespace=self.namespace, status=self.active)
        address.parent = address._get_closest_parent()  # pylint: disable=protected-access
        self.pending.add(address)
        self.pending.add_through(IPAddressToInterface(ip_address=address, interface_id=interface.pk))
        device.primary_ip4 = address
        self.pending.defer_update(device, ["primary_ip4"])

        self.pending.flush()

        self.assertEqual(str(Device.objects.get(pk=device.pk).primary_ip4.host), "10.0.0.5")

    # --- bookkeeping ---

    def test_counts_report_what_is_waiting(self):
        location = self.pending.add(self.build_location("counted"))
        self.pending.add(self.build_device("counted-device", location))
        self.assertEqual(self.pending.counts(), {"Location": 1, "Device": 1})
        self.assertEqual(len(self.pending), 2)

    def test_flushing_empties_the_collector(self):
        self.pending.add(self.build_location("emptied"))
        self.assertEqual(self.pending.flush(), 1)
        self.assertEqual(len(self.pending), 0)
        self.assertEqual(self.pending.flush(), 0)

    # --- refusal handling ---

    def test_one_bad_row_does_not_lose_the_rest_of_its_batch(self):
        """A batch is all or nothing, so a refused one is retried an object at a time.

        Uses a duplicate Interface name, which `dcim_interface_device_name_unique` refuses in the
        database rather than only in `clean()`.
        """
        location = self.pending.add(self.build_location("refusal"))
        device = self.pending.add(self.build_device("refusal-device", location))
        good = self.pending.add(self.build_interface("eth0", device))
        self.pending.add(self.build_interface("eth1", device))
        self.pending.add(self.build_interface("eth1", device))  # a second eth1 on the same Device
        another = self.pending.add(self.build_interface("eth2", device))

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.pending.flush()

        # The Location and Device are their own batches and are unaffected.
        self.assertTrue(Device.objects.filter(pk=device.pk).exists())
        # Of the four Interfaces, the three distinct names survive the retry.
        self.assertEqual(
            sorted(Interface.objects.filter(device_id=device.pk).values_list("name", flat=True)),
            ["eth0", "eth1", "eth2"],
        )
        self.assertTrue(Interface.objects.filter(pk=good.pk).exists())
        self.assertTrue(Interface.objects.filter(pk=another.pk).exists())
        self.assertTrue(any("eth1" in line for line in logs.output), logs.output)

    def test_a_batch_is_split_by_batch_size(self):
        pending = PendingWrites(batch_size=2)
        for index in range(5):
            pending.add(self.build_location(f"batched{index}"))
        self.assertEqual(pending.flush(), 5)
        self.assertEqual(Location.objects.filter(name__startswith="batched").count(), 5)
