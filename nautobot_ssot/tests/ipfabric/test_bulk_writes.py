# One module holds every bulk mode write test  #  pylint: disable=too-many-lines
"""Tests for the batched write collector used by bulk write mode.

These write against the real database, since what is being tested is whether a batched insert built
this way produces the same rows a per-object save would.
"""

import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase, TransactionTestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import Cable as NautobotCable
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import CustomField, Role, Status, Tag, TaggedItem
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
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Cable as CableModel
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Device as DeviceModel
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import Interface as InterfaceModel
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


class PendingWritesTestCase(TestCase):  # pylint: disable=too-many-public-methods
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

    def build_address(self, address):
        """Return an unsaved IPAddress with the parent Prefix a batched insert has to be handed.

        Built through the helper the sync itself uses, so that the way the parent is resolved stays
        in one place rather than being reproduced here against Nautobot's internals.
        """
        return nbutils.resolve_new_ip(address, self.active)

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
        address = self.pending.add(self.build_address("10.0.0.1/24"))
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
        address = self.pending.add(self.build_address("10.0.0.5/24"))
        self.pending.add_through(IPAddressToInterface(ip_address=address, interface_id=interface.pk))
        self.pending.defer_update(device, {"primary_ip4": address})

        self.pending.flush()

        self.assertEqual(str(Device.objects.get(pk=device.pk).primary_ip4.host), "10.0.0.5")

    def test_a_deferred_value_is_not_set_until_the_update_is_applied(self):
        """Queued now, the value would go in with the object's own insert, before what it points at.

        Setting it at queue time is what wrote a Device holding a foreign key to an IP Address that
        had not been inserted yet.
        """
        location = self.pending.add(self.build_location("unset"))
        device = self.pending.add(self.build_device("unset-device", location))
        address = self.pending.add(self.build_address("10.0.0.6/24"))

        self.pending.defer_update(device, {"primary_ip4": address})

        self.assertIsNone(device.primary_ip4)

    def _duplicate_addresses(self):
        """Queue two IPAddress objects for one address, the second of which the database refuses.

        Nautobot makes an address unique within its parent Prefix.
        """
        first = self.pending.add(self.build_address("10.0.0.7/24"))
        duplicate = self.pending.add(self.build_address("10.0.0.7/24"))
        return first, duplicate

    def test_a_join_row_is_dropped_when_the_object_it_points_at_is_refused(self):
        """Writing it anyway leaves a foreign key pointing at nothing.

        PostgreSQL only checks that at `COMMIT`, which belongs to whichever operation triggered the
        flush, so the row that gets reported is not the one at fault and the job ends.
        """
        location = self.pending.add(self.build_location("orphan-join"))
        device = self.pending.add(self.build_device("orphan-join-device", location))
        interface = self.pending.add(self.build_interface("eth0", device))
        _first, duplicate = self._duplicate_addresses()
        self.pending.add_through(IPAddressToInterface(ip_address=duplicate, interface_id=interface.pk))

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.pending.flush()

        self.assertEqual(IPAddress.objects.filter(host="10.0.0.7").count(), 1)
        self.assertFalse(IPAddressToInterface.objects.filter(ip_address_id=duplicate.pk).exists())
        self.assertIn("could not be written", " ".join(logs.output))

    def test_a_deferred_update_is_dropped_when_the_value_it_sets_is_refused(self):
        location = self.pending.add(self.build_location("orphan-update"))
        device = self.pending.add(self.build_device("orphan-update-device", location))
        _first, duplicate = self._duplicate_addresses()
        self.pending.defer_update(device, {"primary_ip4": duplicate})

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.pending.flush()

        self.assertIsNone(Device.objects.get(pk=device.pk).primary_ip4)
        self.assertIn("primary_ip4", " ".join(logs.output))

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

        Uses a duplicate address, which every version this app supports refuses in the database
        through `unique_together` on an IP Address's parent and host, rather than only in `clean()`.
        """
        good = self.pending.add(self.build_address("10.0.0.11/24"))
        self.pending.add(self.build_address("10.0.0.12/24"))
        self.pending.add(self.build_address("10.0.0.12/24"))  # the same address a second time
        another = self.pending.add(self.build_address("10.0.0.13/24"))

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.pending.flush()

        # The three distinct addresses survive the retry, and the duplicate is named.
        queued = ["10.0.0.11", "10.0.0.12", "10.0.0.13"]
        self.assertEqual(
            sorted(str(each.host) for each in IPAddress.objects.filter(host__in=queued)),
            queued,
        )
        self.assertTrue(IPAddress.objects.filter(pk=good.pk).exists())
        self.assertTrue(IPAddress.objects.filter(pk=another.pk).exists())
        self.assertTrue(any("10.0.0.12" in line for line in logs.output), logs.output)

    def test_a_batch_is_split_by_batch_size(self):
        pending = PendingWrites(batch_size=2)
        for index in range(5):
            pending.add(self.build_location(f"batched{index}"))
        self.assertEqual(pending.flush(), 5)
        self.assertEqual(Location.objects.filter(name__startswith="batched").count(), 5)


class BulkModeInterfaceTestCase(TestCase):
    """Test that a bulk mode Interface create lands the same rows a per-object one does."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        self.namespace = get_default_namespace()
        Prefix.objects.get_or_create(
            prefix="10.0.0.0/8",
            namespace=self.namespace,
            defaults={"status": self.active, "type": PrefixTypeChoices.TYPE_NETWORK},
        )
        device_ct = ContentType.objects.get_for_model(Device)
        interface_ct = ContentType.objects.get_for_model(Interface)
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        ssot_tag.content_types.add(device_ct, interface_ct, ContentType.objects.get_for_model(IPAddress))
        Tag.objects.get_or_create(
            name="SSoT Safe Delete", defaults={"color": ColorChoices.COLOR_RED, "description": "Safe delete"}
        )
        role = Role.objects.create(name="mode-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="mode-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="mode-site1", location_type=location_type, status=self.active)
        manufacturer = Manufacturer.objects.create(name="mode-vendor")
        device_type = DeviceType.objects.create(model="mode-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="mode-device",
            status=self.active,
            role=role,
            location=location,
            device_type=device_type,
            serial="serial",
        )
        self.device.tags.add(ssot_tag)

    def adapter(self, bulk_write_mode):
        """Return an adapter in the given mode, with a mocked job."""
        job = unittest.mock.MagicMock()
        job.debug = False
        return NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=bulk_write_mode,
        )

    def create_interface(self, adapter, name, address):
        """Run the DiffSync Interface create for an Interface carrying an address."""
        return InterfaceModel.create(
            adapter,
            ids={"name": name, "device_name": self.device.name},
            attrs={
                "ip_address": address,
                "subnet_mask": "255.255.255.0",
                "status": "Active",
                "type": "1000base-t",
                "ip_is_primary": True,
            },
        )

    def rows_for(self, name):
        """Return the state worth comparing between the two modes."""
        interface = Interface.objects.get(device=self.device, name=name)
        address = interface.ip_addresses.get()
        self.device.refresh_from_db()
        return {
            "interface_tagged": interface.tags.filter(name="SSoT Synced from IPFabric").exists(),
            "interface_stamped": interface.cf.get("system_of_record"),
            "interface_type": interface.type,
            "address": str(address.host),
            "address_mask": address.mask_length,
            "address_parent": str(address.parent.prefix),
            "address_tagged": address.tags.filter(name="SSoT Synced from IPFabric").exists(),
            "address_stamped": address.cf.get("system_of_record"),
            "primary_ip": str(self.device.primary_ip4.host),
        }

    def test_one_address_on_two_interfaces_is_queued_once(self):
        """IP Fabric reports a shared address on each Interface holding it.

        The address is unique within its Prefix, so queueing a second one has the database refuse it
        and leaves its Interface assignment pointing at a row that was never written.
        """
        adapter = self.adapter(bulk_write_mode=True)
        self.create_interface(adapter, "eth0", "10.0.0.9")
        self.create_interface(adapter, "eth1", "10.0.0.9")

        adapter.flush_pending_writes()

        address = IPAddress.objects.get(host="10.0.0.9")
        self.assertEqual(sorted(interface.name for interface in address.interfaces.all()), ["eth0", "eth1"])

    def test_bulk_mode_lands_the_same_rows(self):
        """Every field a per-object write produces has to come out of the batched one too."""
        self.create_interface(self.adapter(bulk_write_mode=False), "eth0", "10.0.0.1")
        per_object = self.rows_for("eth0")

        bulk_adapter = self.adapter(bulk_write_mode=True)
        self.create_interface(bulk_adapter, "eth1", "10.0.0.2")
        # Nothing is written until the flush.
        self.assertFalse(Interface.objects.filter(device=self.device, name="eth1").exists())
        bulk_adapter.flush_pending_writes()
        batched = self.rows_for("eth1")

        # The two addresses differ by design; everything else must match.
        for key, expected in per_object.items():
            if key in ("address", "primary_ip"):
                continue
            self.assertEqual(batched[key], expected, f"{key} differs between the two modes")
        self.assertEqual(batched["address"], "10.0.0.2")
        self.assertEqual(batched["primary_ip"], "10.0.0.2")

    def test_nothing_is_written_before_the_flush(self):
        adapter = self.adapter(bulk_write_mode=True)
        self.create_interface(adapter, "eth5", "10.0.0.5")
        self.assertEqual(Interface.objects.filter(device=self.device).count(), 0)
        self.assertEqual(
            adapter.pending.counts(),
            {"Interface": 1, "IPAddress": 1, "TaggedItem": 2, "IPAddressToInterface": 1, "field updates": 1},
        )

    def test_an_address_nautobot_already_holds_is_reused(self):
        """A re-sync must not try to insert an address that exists."""
        existing = IPAddress(address="10.0.0.9/24", namespace=self.namespace, status=self.active)
        existing.validated_save()

        adapter = self.adapter(bulk_write_mode=True)
        self.create_interface(adapter, "eth9", "10.0.0.9")
        adapter.flush_pending_writes()

        self.assertEqual(IPAddress.objects.filter(host="10.0.0.9").count(), 1)
        interface = Interface.objects.get(device=self.device, name="eth9")
        self.assertEqual(interface.ip_addresses.get().pk, existing.pk)


class BulkModeLocationAndVlanTestCase(TestCase):
    """Test the Location and VLAN bulk paths, and that a queued parent is found rather than rebuilt."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        # `get_or_create_location_object` looks for a LocationType named exactly "Site".
        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(device_ct, ContentType.objects.get_for_model(VLAN))
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        ssot_tag.content_types.add(
            device_ct, ContentType.objects.get_for_model(Location), ContentType.objects.get_for_model(VLAN)
        )
        self.pending = PendingWrites()

    def test_a_queued_location_is_found_rather_than_queued_twice(self):
        """Two callers asking for the same Location must not each build one.

        `Location.create` asks with the site id and `Device.create` without it, so relying on the
        lookup cache alone would build two and write both.
        """
        first = nbutils.get_or_create_location_object(location_name="dup", location_id="site-9", pending=self.pending)
        second = nbutils.get_or_create_location_object(location_name="dup", location_id=None, pending=self.pending)

        self.assertIs(second, first, "The second caller should have been given the queued Location.")
        self.pending.flush()
        self.assertEqual(Location.objects.filter(name="dup").count(), 1)

    def test_a_queued_location_carries_its_site_id_and_tag(self):
        location = nbutils.get_or_create_location_object(
            location_name="stamped", location_id="site-7", pending=self.pending
        )
        self.pending.flush()

        written = Location.objects.get(pk=location.pk)
        self.assertEqual(written.cf["ipfabric_site_id"], "site-7")
        self.assertEqual(written.cf["system_of_record"], "IPFabric")
        self.assertTrue(written.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_a_queued_vlan_gets_its_location_and_tag(self):
        """`VLAN.save()` makes the location assignment, and a batched insert never calls it."""
        location = nbutils.get_or_create_location_object(location_name="vlan-home", pending=self.pending)
        vlan = nbutils.create_vlan(
            vlan_name="bulk-vlan",
            vlan_id=42,
            vlan_status="Active",
            location_obj=location,
            description="queued",
            pending=self.pending,
        )
        self.pending.flush()

        written = VLAN.objects.get(pk=vlan.pk)
        self.assertEqual([each.name for each in written.locations.all()], ["vlan-home"])
        self.assertEqual(written.description, "queued")
        self.assertEqual(written.cf["system_of_record"], "IPFabric")
        self.assertTrue(written.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_a_vlan_and_its_location_land_in_one_flush(self):
        """The VLAN references a Location that has not been written when the VLAN is built."""
        location = nbutils.get_or_create_location_object(location_name="same-flush", pending=self.pending)
        self.assertFalse(Location.objects.filter(name="same-flush").exists())
        vlan = nbutils.create_vlan(
            vlan_name="same-flush-vlan",
            vlan_id=43,
            vlan_status="Active",
            location_obj=location,
            description="",
            pending=self.pending,
        )

        self.pending.flush()

        self.assertEqual([each.name for each in VLAN.objects.get(pk=vlan.pk).locations.all()], ["same-flush"])

    def test_an_existing_location_is_not_queued(self):
        """A re-sync must re-stamp what Nautobot holds rather than queue a second row."""
        existing = Location.objects.create(
            name="already-there", location_type=LocationType.objects.get(name="Site"), status=self.active
        )
        found = nbutils.get_or_create_location_object(location_name="already-there", pending=self.pending)

        self.assertEqual(found.pk, existing.pk)
        self.assertEqual(self.pending.counts(), {}, "Nothing should have been queued for an existing Location.")


class BulkModeDeviceTestCase(TestCase):
    """Test the Device bulk path, including an Interface hung off a Device that is only queued."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(device_ct, ContentType.objects.get_for_model(VLAN))
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        ssot_tag.content_types.add(
            device_ct,
            ContentType.objects.get_for_model(Interface),
            ContentType.objects.get_for_model(Location),
        )
        self.role = Role.objects.create(name="dev-role")
        self.role.content_types.add(device_ct)
        # `get_or_create_device_role_object` matches on this custom field.
        role_cf, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT, key="ipfabric_type", defaults={"label": "IPFabric Type"}
        )
        role_cf.content_types.add(ContentType.objects.get_for_model(Role))
        self.role.cf["ipfabric_type"] = "dev-role"
        self.role.validated_save()
        manufacturer = Manufacturer.objects.create(name="dev-vendor")
        DeviceType.objects.create(model="dev-model", manufacturer=manufacturer)
        self.location = Location.objects.create(name="dev-site", location_type=site_type, status=self.active)

    def adapter(self, bulk_write_mode):
        """Return an adapter in the given mode, with a mocked job."""
        job = unittest.mock.MagicMock()
        job.debug = False
        return NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=bulk_write_mode,
        )

    def device_attrs(self, **overrides):
        """Return the attrs an IP Fabric Device create supplies."""
        attrs = {
            "location_name": "dev-site",
            "model": "dev-model",
            "vendor": "dev-vendor",
            "role": "dev-role",
            "status": "Active",
            "platform": None,
            "serial_number": "abc123",
        }
        attrs.update(overrides)
        return attrs

    def test_a_queued_device_lands_tagged_and_stamped(self):
        adapter = self.adapter(bulk_write_mode=True)
        DeviceModel.create(adapter, ids={"name": "queued-dev"}, attrs=self.device_attrs())
        self.assertFalse(Device.objects.filter(name="queued-dev").exists())

        adapter.flush_pending_writes()

        written = Device.objects.get(name="queued-dev")
        self.assertEqual(written.location.name, "dev-site")
        self.assertEqual(written.serial, "abc123")
        self.assertEqual(written.cf["system_of_record"], "IPFabric")
        self.assertTrue(written.tags.filter(name="SSoT Synced from IPFabric").exists())

    def test_an_interface_is_hung_off_a_queued_device(self):
        """`Interface.create` looks its Device up by name, which has to find the queued one."""
        adapter = self.adapter(bulk_write_mode=True)
        DeviceModel.create(adapter, ids={"name": "parent-dev"}, attrs=self.device_attrs())
        InterfaceModel.create(
            adapter,
            ids={"name": "eth0", "device_name": "parent-dev"},
            attrs={"ip_address": None, "subnet_mask": None, "status": "Active", "type": "1000base-t"},
        )

        adapter.flush_pending_writes()

        interface = Interface.objects.get(name="eth0")
        self.assertEqual(interface.device.name, "parent-dev")

    def test_a_cable_terminates_on_devices_queued_in_the_same_run(self):
        """Cables read their Interfaces back from the database, so the queue has to be written first.

        The Devices and Interfaces a link terminates on are created earlier in the same sync. In bulk
        mode that leaves them queued, and a Cable cannot terminate on a row that does not exist.
        """
        adapter = self.adapter(bulk_write_mode=True)
        for device_name in ("cable-dev-a", "cable-dev-b"):
            DeviceModel.create(adapter, ids={"name": device_name}, attrs=self.device_attrs())
            InterfaceModel.create(
                adapter,
                ids={"name": "eth0", "device_name": device_name},
                attrs={"ip_address": None, "subnet_mask": None, "status": "Active", "type": "1000base-t"},
            )
        self.assertFalse(Device.objects.filter(name="cable-dev-a").exists())

        CableModel.create(
            adapter,
            ids={
                "termination_a_device": "cable-dev-a",
                "termination_a_name": "eth0",
                "termination_b_device": "cable-dev-b",
                "termination_b_name": "eth0",
            },
            attrs={"status": "Connected"},
        )

        cable = NautobotCable.objects.get()
        self.assertEqual(
            {cable.termination_a.device.name, cable.termination_b.device.name},
            {"cable-dev-a", "cable-dev-b"},
        )

    def test_a_flush_empties_the_lookups_that_read_what_it_wrote(self):
        """A lookup that ran before the flush cached an answer the flush has invalidated."""
        adapter = self.adapter(bulk_write_mode=True)
        DeviceModel.create(adapter, ids={"name": "stale-dev"}, attrs=self.device_attrs())
        self.assertIsNone(nbutils.get_syncable_device("stale-dev"))

        adapter.flush_pending_writes()

        self.assertIsNotNone(nbutils.get_syncable_device("stale-dev"))

    def test_a_virtual_chassis_master_is_applied_after_its_device(self):
        """The master points back at the Device, so it cannot be set until the Device exists."""
        adapter = self.adapter(bulk_write_mode=True)
        DeviceModel.create(
            adapter,
            ids={"name": "stack-member"},
            attrs=self.device_attrs(vc_name="stack-1", vc_master=True, vc_position=1, vc_priority=1),
        )

        adapter.flush_pending_writes()

        device = Device.objects.get(name="stack-member")
        self.assertEqual(device.virtual_chassis.name, "stack-1")
        self.assertEqual(device.vc_position, 1)
        self.assertEqual(device.virtual_chassis.master, device)

    def test_bulk_mode_lands_what_per_object_mode_does(self):
        DeviceModel.create(self.adapter(bulk_write_mode=False), ids={"name": "per-object"}, attrs=self.device_attrs())
        bulk_adapter = self.adapter(bulk_write_mode=True)
        DeviceModel.create(bulk_adapter, ids={"name": "batched"}, attrs=self.device_attrs())
        bulk_adapter.flush_pending_writes()

        def state(name):
            device = Device.objects.get(name=name)
            return {
                "location": device.location.name,
                "role": device.role.name,
                "device_type": device.device_type.model,
                "serial": device.serial,
                "status": device.status.name,
                "stamped": device.cf["system_of_record"],
                "tagged": device.tags.filter(name="SSoT Synced from IPFabric").exists(),
            }

        self.assertEqual(state("batched"), state("per-object"))


class HighWaterFlushTestCase(TestCase):
    """Test that a queue written part way through a sync loses nothing."""

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        site_type, _ = LocationType.objects.get_or_create(name="Site")
        site_type.content_types.add(device_ct, ContentType.objects.get_for_model(VLAN))
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        ssot_tag.content_types.add(
            device_ct, ContentType.objects.get_for_model(Interface), ContentType.objects.get_for_model(Location)
        )
        role = Role.objects.create(name="hw-role")
        role.content_types.add(device_ct)
        role_cf, _ = CustomField.objects.get_or_create(
            type=CustomFieldTypeChoices.TYPE_TEXT, key="ipfabric_type", defaults={"label": "IPFabric Type"}
        )
        role_cf.content_types.add(ContentType.objects.get_for_model(Role))
        role.cf["ipfabric_type"] = "hw-role"
        role.validated_save()
        manufacturer = Manufacturer.objects.create(name="hw-vendor")
        DeviceType.objects.create(model="hw-model", manufacturer=manufacturer)
        Location.objects.create(name="hw-site", location_type=site_type, status=self.active)
        job = unittest.mock.MagicMock()
        job.debug = False
        self.adapter = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=True,
        )

    def test_the_queue_is_written_once_it_grows_past_the_ceiling(self):
        """Otherwise a hundred thousand Interfaces are all held until the end of the sync."""
        DeviceModel.create(
            self.adapter,
            ids={"name": "hw-dev"},
            attrs={
                "location_name": "hw-site",
                "model": "hw-model",
                "vendor": "hw-vendor",
                "role": "hw-role",
                "status": "Active",
                "platform": None,
                "serial_number": "s",
            },
        )
        with unittest.mock.patch(
            "nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot.PENDING_WRITE_HIGH_WATER", 4
        ):
            for index in range(6):
                InterfaceModel.create(
                    self.adapter,
                    ids={"name": f"eth{index}", "device_name": "hw-dev"},
                    attrs={"ip_address": None, "subnet_mask": None, "status": "Active", "type": "1000base-t"},
                )

        # Some Interfaces landed before the sync finished, rather than all of them waiting.
        self.assertGreater(Interface.objects.filter(device__name="hw-dev").count(), 0)
        self.adapter.flush_pending_writes()
        self.assertEqual(Interface.objects.filter(device__name="hw-dev").count(), 6)

    def test_a_mid_sync_flush_does_not_lose_what_is_set_after_queueing(self):
        """A Device's chassis fields are set after it is queued, so an early flush would drop them.

        The flush is triggered from `super().create()`, once the model has finished, which is what
        makes that impossible.
        """
        with unittest.mock.patch(
            "nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot.PENDING_WRITE_HIGH_WATER", 1
        ):
            DeviceModel.create(
                self.adapter,
                ids={"name": "hw-stack"},
                attrs={
                    "location_name": "hw-site",
                    "model": "hw-model",
                    "vendor": "hw-vendor",
                    "role": "hw-role",
                    "status": "Active",
                    "platform": None,
                    "serial_number": "s",
                    "vc_name": "hw-chassis",
                    "vc_master": True,
                    "vc_position": 2,
                    "vc_priority": 3,
                },
            )
        self.adapter.flush_pending_writes()

        device = Device.objects.get(name="hw-stack")
        self.assertEqual(device.virtual_chassis.name, "hw-chassis")
        self.assertEqual(device.vc_position, 2, "The chassis position was set after queueing and must survive.")
        self.assertEqual(device.vc_priority, 3)
        self.assertEqual(device.virtual_chassis.master, device)

    def test_an_interface_still_finds_its_device_after_a_flush(self):
        """Once flushed the Device is in the database, so the lookup has to fall through to it."""
        DeviceModel.create(
            self.adapter,
            ids={"name": "flushed-dev"},
            attrs={
                "location_name": "hw-site",
                "model": "hw-model",
                "vendor": "hw-vendor",
                "role": "hw-role",
                "status": "Active",
                "platform": None,
                "serial_number": "s",
            },
        )
        self.adapter.flush_pending_writes()
        self.assertTrue(Device.objects.filter(name="flushed-dev").exists())

        InterfaceModel.create(
            self.adapter,
            ids={"name": "after-flush", "device_name": "flushed-dev"},
            attrs={"ip_address": None, "subnet_mask": None, "status": "Active", "type": "1000base-t"},
        )
        self.adapter.flush_pending_writes()

        self.assertEqual(Interface.objects.get(name="after-flush").device.name, "flushed-dev")


class MissingParentPrefixTestCase(TestCase):
    """Test that an address whose subnet Nautobot does not hold is still created.

    IP Fabric reports addresses without the subnets they sit in, so the first address a sync sees
    from a subnet has no parent Prefix. Both write paths have to make one; the batched path did not,
    and dropped every such address with "No suitable parent Prefix ... exists in Namespace Global".
    """

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric",
            defaults={"color": ColorChoices.COLOR_LIGHT_GREEN, "description": "Synced"},
        )
        ssot_tag.content_types.add(
            device_ct, ContentType.objects.get_for_model(Interface), ContentType.objects.get_for_model(IPAddress)
        )
        Tag.objects.get_or_create(
            name="SSoT Safe Delete", defaults={"color": ColorChoices.COLOR_RED, "description": "Safe delete"}
        )
        role = Role.objects.create(name="prefix-role")
        role.content_types.add(device_ct)
        location_type, _ = LocationType.objects.get_or_create(name="prefix-site")
        location_type.content_types.add(device_ct)
        location = Location.objects.create(name="prefix-site1", location_type=location_type, status=self.active)
        manufacturer = Manufacturer.objects.create(name="prefix-vendor")
        device_type = DeviceType.objects.create(model="prefix-model", manufacturer=manufacturer)
        self.device = Device.objects.create(
            name="prefix-device",
            status=self.active,
            role=role,
            location=location,
            device_type=device_type,
            serial="serial",
        )
        self.device.tags.add(ssot_tag)

    def adapter(self, bulk_write_mode):
        """Return an adapter in the given mode, with a mocked job."""
        job = unittest.mock.MagicMock()
        job.debug = False
        return NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=bulk_write_mode,
        )

    def create_addressed_interface(self, adapter, name, address, mask):
        """Run the DiffSync Interface create for an Interface carrying an address."""
        return InterfaceModel.create(
            adapter,
            ids={"name": name, "device_name": self.device.name},
            attrs={"ip_address": address, "subnet_mask": mask, "status": "Active", "type": "1000base-t"},
        )

    def test_the_parent_prefix_is_created_in_bulk_mode(self):
        self.assertFalse(Prefix.objects.filter(prefix="172.31.16.0/20").exists())

        adapter = self.adapter(bulk_write_mode=True)
        self.create_addressed_interface(adapter, "eth0", "172.31.16.1", "255.255.240.0")
        adapter.flush_pending_writes()

        self.assertTrue(Prefix.objects.filter(prefix="172.31.16.0/20").exists())
        address = IPAddress.objects.get(host="172.31.16.1")
        self.assertEqual(str(address.parent.prefix), "172.31.16.0/20")
        self.assertEqual(
            [str(each.host) for each in Interface.objects.get(name="eth0").ip_addresses.all()], ["172.31.16.1"]
        )
        adapter.job.logger.error.assert_not_called()

    def test_the_parent_prefix_is_created_in_per_object_mode(self):
        """The path that already worked, kept covered now that both share one helper."""
        adapter = self.adapter(bulk_write_mode=False)
        self.create_addressed_interface(adapter, "eth1", "172.31.32.1", "255.255.240.0")

        self.assertTrue(Prefix.objects.filter(prefix="172.31.32.0/20").exists())
        self.assertEqual(str(IPAddress.objects.get(host="172.31.32.1").parent.prefix), "172.31.32.0/20")

    def test_both_modes_agree_on_the_prefix_they_make(self):
        """One helper serves both, so the Prefix must come out the same either way."""
        self.create_addressed_interface(self.adapter(bulk_write_mode=False), "eth2", "10.40.0.1", "255.255.255.0")
        bulk_adapter = self.adapter(bulk_write_mode=True)
        self.create_addressed_interface(bulk_adapter, "eth3", "10.41.0.1", "255.255.255.0")
        bulk_adapter.flush_pending_writes()

        def prefix_state(network):
            prefix = Prefix.objects.get(prefix=network)
            return {"type": prefix.type, "status": prefix.status.name, "namespace": prefix.namespace.name}

        self.assertEqual(prefix_state("10.41.0.0/24"), prefix_state("10.40.0.0/24"))

    def test_a_second_address_in_the_same_subnet_reuses_the_prefix(self):
        adapter = self.adapter(bulk_write_mode=True)
        self.create_addressed_interface(adapter, "eth4", "192.168.5.1", "255.255.255.0")
        self.create_addressed_interface(adapter, "eth5", "192.168.5.2", "255.255.255.0")
        adapter.flush_pending_writes()

        self.assertEqual(Prefix.objects.filter(prefix="192.168.5.0/24").count(), 1)
        self.assertEqual(IPAddress.objects.filter(host__in=["192.168.5.1", "192.168.5.2"]).count(), 2)


class NewAddressResolutionTestCase(TestCase):
    """Test how an IP Address is resolved, which both write paths share.

    Asserted through the behaviour a caller sees, and in both modes, since the two go through the
    same resolution.
    """

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        self.namespace = get_default_namespace()
        self.logger = unittest.mock.MagicMock()

    def status_for_ip(self):
        """Return the Status a synced address is given."""
        return nbutils.get_status_for_model(IPAddress, "Active")

    def make_prefix(self, network):
        """Create a Prefix, as another system or an earlier sync would have."""
        prefix, _ = Prefix.objects.get_or_create(
            prefix=network,
            namespace=self.namespace,
            defaults={"status": self.active, "type": PrefixTypeChoices.TYPE_NETWORK},
        )
        return prefix

    def errors(self):
        """Return the error messages logged."""
        return [str(call.args[0]) for call in self.logger.error.call_args_list]

    # --- the reported failure ---

    def test_an_address_covered_only_by_a_narrower_prefix(self):
        """The reported case: IP Fabric reports a /24 mask where only a /25 covers the address.

        Nautobot's own parent determination refuses a Prefix longer than the address's mask, so
        leaving it to work the parent out rejected the address and named the very Prefix it wanted.
        """
        self.make_prefix("10.0.0.0/25")

        for label, pending in (("per object", None), ("bulk", PendingWrites())):
            with self.subTest(mode=label):
                address = f"10.0.{0 if pending is None else 1}.1"
                self.make_prefix(f"10.0.{0 if pending is None else 1}.0/25")
                result = nbutils.create_ip(address, "255.255.255.0", logger=self.logger, pending=pending)
                if pending is not None:
                    pending.flush()

                self.assertIsNotNone(result, f"{label}: the address should have been created")
                written = IPAddress.objects.get(host=address)
                self.assertEqual(str(written.parent.prefix), f"10.0.{0 if pending is None else 1}.0/25")
                self.assertEqual(self.errors(), [])

    def test_no_unnecessary_prefix_is_created(self):
        """A wider Prefix does not help, since the address parents to the most specific one."""
        self.make_prefix("10.5.0.0/25")

        nbutils.create_ip("10.5.0.1", "255.255.255.0", logger=self.logger)

        self.assertFalse(
            Prefix.objects.filter(prefix="10.5.0.0/24").exists(),
            "A /25 already covers the address, so no /24 should have been made.",
        )

    # --- the ordinary paths ---

    def test_the_parent_prefix_is_created_when_nothing_covers_the_address(self):
        for label, pending in (("per object", None), ("bulk", PendingWrites())):
            with self.subTest(mode=label):
                octet = 10 if pending is None else 11
                result = nbutils.create_ip(f"10.{octet}.0.1", "255.255.255.0", logger=self.logger, pending=pending)
                if pending is not None:
                    pending.flush()

                self.assertIsNotNone(result)
                self.assertTrue(Prefix.objects.filter(prefix=f"10.{octet}.0.0/24").exists())
                self.assertEqual(str(IPAddress.objects.get(host=f"10.{octet}.0.1").parent.prefix), f"10.{octet}.0.0/24")

    def test_an_address_nautobot_already_holds_is_reused(self):
        self.make_prefix("10.20.0.0/24")
        existing = IPAddress(address="10.20.0.1/24", namespace=self.namespace, status=self.active)
        existing.validated_save()

        result = nbutils.create_ip("10.20.0.1", "255.255.255.0", logger=self.logger)

        self.assertEqual(result.pk, existing.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.20.0.1").count(), 1)

    def test_an_address_the_prefix_cannot_be_made_for_is_reported(self):
        """A Prefix that cannot be created leaves the address unwritten, and says so."""
        with unittest.mock.patch.object(
            nbutils.Prefix.objects, "get_or_create", side_effect=nbutils.ValidationError("refused")
        ):
            result = nbutils.create_ip("10.30.0.1", "255.255.255.0", logger=self.logger)

        self.assertIsNone(result)
        self.assertTrue(any("Unable to create a missing Prefix" in line for line in self.errors()), self.errors())

    def test_a_status_that_does_not_exist_is_reported(self):
        result = nbutils.create_ip("10.40.0.1", "255.255.255.0", status="No-Such-Status", logger=self.logger)

        self.assertIsNone(result)
        self.assertTrue(any("No-Such-Status" in line for line in self.errors()), self.errors())

    def test_an_address_nautobot_holds_under_another_mask_is_reused(self):
        """IP Fabric's mask for an address need not be the one Nautobot holds it under.

        The uniqueness Nautobot enforces covers the parent Prefix and the host, not the mask, so
        matching on the address alone finds nothing and the insert is then refused.
        """
        self.make_prefix("10.50.0.0/25")
        existing = IPAddress(address="10.50.0.1/25", namespace=self.namespace, status=self.active)
        existing.validated_save()

        result = nbutils.create_ip("10.50.0.1", "255.255.255.0", logger=self.logger)

        self.assertEqual(result.pk, existing.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.50.0.1").count(), 1)
        self.assertEqual(self.errors(), [])

    def test_an_address_held_under_another_mask_is_reused_in_bulk_mode_too(self):
        self.make_prefix("10.52.0.0/25")
        existing = IPAddress(address="10.52.0.1/25", namespace=self.namespace, status=self.active)
        existing.validated_save()
        pending = PendingWrites()

        result = nbutils.create_ip("10.52.0.1", "255.255.255.0", logger=self.logger, pending=pending)
        pending.flush()

        self.assertEqual(result.pk, existing.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.52.0.1").count(), 1)
        self.assertEqual(self.errors(), [])

    def test_one_host_reported_with_two_masks_is_written_once(self):
        """Both reports resolve to the same parent, so the second would be refused as a duplicate."""
        self.make_prefix("10.53.0.0/25")
        pending = PendingWrites()

        first = nbutils.create_ip("10.53.0.1", "255.255.255.128", logger=self.logger, pending=pending)
        second = nbutils.create_ip("10.53.0.1", "255.255.255.0", logger=self.logger, pending=pending)
        pending.flush()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.53.0.1").count(), 1)
        self.assertEqual(self.errors(), [])

    def test_no_wider_prefix_is_created_for_an_address_nautobot_already_holds(self):
        """A wider Prefix could never be the parent anyway, as the most specific containing one wins.

        Nautobot 3.2 reports a duplicate address from `clean()`, and reading that as a missing Prefix
        is what created one.
        """
        self.make_prefix("10.54.0.0/25")
        existing = IPAddress(address="10.54.0.1/25", namespace=self.namespace, status=self.active)
        existing.validated_save()

        nbutils.create_ip("10.54.0.1", "255.255.255.0", logger=self.logger)

        self.assertEqual(
            sorted(str(prefix.prefix) for prefix in Prefix.objects.filter(network="10.54.0.0")),
            ["10.54.0.0/25"],
        )

    def test_the_mask_of_a_reused_address_is_corrected(self):
        """IP Fabric reports the subnet an address sits in, and that mask is what the sync keeps.

        Left as Nautobot holds it, the difference is reported on every run and never settles.
        """
        self.make_prefix("10.55.0.0/25")
        existing = IPAddress(address="10.55.0.1/25", namespace=self.namespace, status=self.active)
        existing.validated_save()

        nbutils.create_ip("10.55.0.1", "255.255.255.0", logger=self.logger)

        self.assertEqual(IPAddress.objects.get(pk=existing.pk).mask_length, 24)
        self.assertEqual(self.errors(), [])

    def test_the_mask_of_a_reused_address_is_corrected_in_bulk_mode_too(self):
        self.make_prefix("10.56.0.0/25")
        existing = IPAddress(address="10.56.0.1/25", namespace=self.namespace, status=self.active)
        existing.validated_save()
        pending = PendingWrites()

        nbutils.create_ip("10.56.0.1", "255.255.255.0", logger=self.logger, pending=pending)
        pending.flush()

        self.assertEqual(IPAddress.objects.get(pk=existing.pk).mask_length, 24)
        self.assertEqual(self.errors(), [])


class CommitTimeRefusalTestCase(TransactionTestCase):
    """Test what a batch does when PostgreSQL refuses it at `COMMIT` rather than at the insert.

    A `TransactionTestCase` rather than a `TestCase` because that is the whole subject. Django
    declares foreign keys `DEFERRABLE INITIALLY DEFERRED`, so a missing target is only detected at
    `COMMIT`, and a `TestCase` wraps everything in a transaction it never commits. A batch that
    breaks a foreign key therefore passes under a `TestCase` and fails in a job.
    """

    def setUp(self):
        super().setUp()
        self.active = Status.objects.get(name="Active")
        device_ct = ContentType.objects.get_for_model(Device)
        self.role = Role.objects.create(name="commit-role")
        self.role.content_types.add(device_ct)
        self.location_type = LocationType.objects.create(name="commit-site")
        self.location_type.content_types.add(device_ct)
        manufacturer = Manufacturer.objects.create(name="commit-vendor")
        self.device_type = DeviceType.objects.create(model="commit-model", manufacturer=manufacturer)
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
        )

    def test_a_device_carries_its_primary_address_although_addresses_are_written_after_devices(self):
        """The address is written after the Device, so the Device cannot hold it at insertion."""
        namespace = get_default_namespace()
        Prefix.objects.create(
            prefix="10.0.0.0/24",
            namespace=namespace,
            status=self.active,
            type=PrefixTypeChoices.TYPE_NETWORK,
        )
        location = self.pending.add(self.build_location("primary-commit"))
        device = self.pending.add(self.build_device("primary-commit-device", location))
        interface = self.pending.add(Interface(device_id=device.pk, name="eth0", status=self.active, type="1000base-t"))
        address = self.pending.add(nbutils.resolve_new_ip("10.0.0.5/24", self.active))
        self.pending.add_through(IPAddressToInterface(ip_address=address, interface_id=interface.pk))
        self.pending.defer_update(device, {"primary_ip4": address})

        self.pending.flush()

        self.assertEqual(str(Device.objects.get(pk=device.pk).primary_ip4.host), "10.0.0.5")

    def test_a_device_batch_refused_at_commit_still_writes_the_devices_it_can(self):
        """A batch refused at `COMMIT` was already marked written, so the retry has to undo that.

        Left marked written, `Device.clean()` reads its own row back and raises `DoesNotExist`,
        which is not a refusal any caller expects and took a whole job down with it.
        """
        location = self.pending.add(self.build_location("retried"))
        good = self.pending.add(self.build_device("retried-good", location))
        # A Location neither queued nor in the database, so the Device pointing at it breaks a
        # foreign key that is only checked at `COMMIT`, by which time the batch looks written.
        bad = self.pending.add(self.build_device("retried-bad", self.build_location("never-written")))

        with self.assertLogs("nautobot.ssot.ipfabric", level="WARNING") as logs:
            self.pending.flush()

        self.assertTrue(Device.objects.filter(pk=good.pk).exists())
        self.assertFalse(Device.objects.filter(pk=bad.pk).exists())
        self.assertIn("retried-bad", " ".join(logs.output))
