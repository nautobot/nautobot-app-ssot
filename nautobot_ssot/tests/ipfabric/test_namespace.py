"""Tests for running the IP Fabric sync in a Namespace other than Global."""

from unittest import mock

from django.apps import apps as global_apps
from nautobot.dcim.models import Device, Interface
from nautobot.ipam.models import VRF, IPAddress, Namespace, Prefix, get_default_namespace
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.diffsync import diffsync_models
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.tests.ipfabric.supporting_objects import SupportingObjectTestCase, addresses_of


def prepare(test):
    """Make the custom fields the sync stamps and a Namespace to choose, and clear the choice after."""
    nautobot_database_ready_callback(sender=None, apps=global_apps)
    test.adapter.tenant = None
    test.adapter.sync_ipfabric_tagged_only = False
    test.addCleanup(nbutils.use_namespace, None)
    return Namespace.objects.create(name="customer-a")


def make_address(address, namespace, status):
    """Create an address, and the Prefix it needs, in the given Namespace."""
    Prefix.objects.get_or_create(prefix="10.0.0.0/24", namespace=namespace, defaults={"status": status})
    return IPAddress.objects.create(address=address, status=status, namespace=namespace)


class TestTheRunsNamespace(SupportingObjectTestCase):
    """Which Namespace a run uses."""

    def setUp(self):
        super().setUp()
        self.namespace = prepare(self)

    def test_global_unless_one_is_chosen(self):
        self.assertFalse(nbutils.namespace_chosen())
        self.assertEqual(nbutils.get_run_namespace(), get_default_namespace())
        self.assertEqual(nbutils.run_namespace_filter(), {})

    def test_the_chosen_one(self):
        nbutils.use_namespace(self.namespace)
        self.assertTrue(nbutils.namespace_chosen())
        self.assertEqual(nbutils.get_run_namespace(), self.namespace)
        self.assertEqual(nbutils.run_namespace_filter(), {"parent__namespace": self.namespace})


class TestWritingInTheChosenNamespace(SupportingObjectTestCase):
    """Addresses, Prefixes and VRFs are written in the chosen Namespace."""

    def setUp(self):
        super().setUp()
        self.namespace = prepare(self)

    def test_an_address_and_its_parent_prefix_are_created_in_it(self):
        nbutils.use_namespace(self.namespace)
        ip_obj = nbutils.create_ip("10.0.0.1", 24)
        self.assertEqual(ip_obj.parent.namespace, self.namespace)
        self.assertFalse(Prefix.objects.filter(namespace=get_default_namespace()).exists())

    def test_the_same_address_in_global_is_left_alone_rather_than_reused(self):
        in_global = make_address("10.0.0.1/24", get_default_namespace(), self.active_status)
        nbutils.use_namespace(self.namespace)
        ip_obj = nbutils.create_ip("10.0.0.1", 24)
        self.assertNotEqual(ip_obj.pk, in_global.pk)
        self.assertEqual(IPAddress.objects.filter(host="10.0.0.1").count(), 2)

    def test_a_queued_address_is_created_in_it_rather_than_reusing_globals(self):
        in_global = make_address("10.0.0.1/24", get_default_namespace(), self.active_status)
        nbutils.use_namespace(self.namespace)
        pending = PendingWrites(mock.MagicMock())
        nbutils.create_ip("10.0.0.1", 24, pending=pending)
        pending.flush()
        ours = IPAddress.objects.exclude(pk=in_global.pk).get(host="10.0.0.1")
        self.assertEqual(ours.parent.namespace, self.namespace)

    def test_without_a_choice_an_exact_match_is_still_reused_from_any_namespace(self):
        elsewhere = make_address("10.0.0.1/24", self.namespace, self.active_status)
        self.assertEqual(nbutils.create_ip("10.0.0.1", 24).pk, elsewhere.pk)

    def test_a_prefix_is_created_in_it(self):
        nbutils.use_namespace(self.namespace)
        self.assertEqual(nbutils.create_prefix("10.1.0.0/24").namespace, self.namespace)
        self.assertTrue(nbutils.covering_prefix_exists("10.1.0.1/32"))
        self.assertEqual(nbutils.get_prefix("10.1.0.0/24").namespace, self.namespace)

    def test_a_prefix_in_global_is_not_adopted(self):
        Prefix.objects.create(prefix="10.1.0.0/24", namespace=get_default_namespace(), status=self.active_status)
        nbutils.use_namespace(self.namespace)
        self.assertIsNone(nbutils.get_prefix("10.1.0.0/24"))
        self.assertFalse(nbutils.covering_prefix_exists("10.1.0.1/32"))

    def test_a_vrf_is_created_and_found_in_it(self):
        VRF.objects.create(name="BLUE", namespace=get_default_namespace(), status=self.active_status)
        nbutils.use_namespace(self.namespace)
        created = nbutils.create_vrf("BLUE", None, "Active", "")
        self.assertEqual(created.namespace, self.namespace)
        self.assertEqual(nbutils.get_vrf("BLUE"), created)

    def test_a_tenants_vrf_is_created_in_it_rather_than_adopting_globals(self):
        in_global = VRF.objects.create(name="BLUE", namespace=get_default_namespace(), status=self.active_status)
        tenant = Tenant.objects.create(name="customer-a")
        nbutils.use_namespace(self.namespace)
        created = nbutils.create_vrf("BLUE", None, "Active", "", tenant=tenant)
        self.assertEqual((created.namespace, created.tenant), (self.namespace, tenant))
        in_global.refresh_from_db()
        self.assertIsNone(in_global.tenant)

    def test_an_ambiguous_vrf_is_reported_with_the_namespace_named(self):
        nbutils.use_namespace(self.namespace)
        for rd in ("65000:1", "65000:2"):
            VRF.objects.create(name="BLUE", rd=rd, namespace=self.namespace, status=self.active_status)
        logger = mock.MagicMock()
        self.assertIsNone(nbutils.get_vrf("BLUE", logger=logger))
        self.assertIn("customer-a", str(logger.error.call_args))


class TestReadingTheChosenNamespace(SupportingObjectTestCase):
    """The Nautobot adapter reads only the chosen Namespace's addresses, Prefixes and VRFs."""

    def setUp(self):
        super().setUp()
        self.namespace = prepare(self)
        self.create_device(name="ours")
        self.interface = Interface.objects.create(
            device=Device.objects.get(name="ours"), name="eth0", type="1000base-t", status=self.active_status
        )

    def nautobot_adapter(self, **overrides):
        """Return a Nautobot adapter with addresses, VRFs and Prefixes in scope."""
        return NautobotDiffSync(
            **overrides,
            job=mock.MagicMock(),
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=SyncScope(["locations", "interfaces", "ip_addresses", "vrfs", "prefixes"]),
            tenant=None,
        )

    def test_only_its_addresses_are_loaded(self):
        self.interface.ip_addresses.add(make_address("10.0.0.1/24", self.namespace, self.active_status))
        self.interface.ip_addresses.add(make_address("10.0.0.2/24", get_default_namespace(), self.active_status))
        nbutils.use_namespace(self.namespace)
        adapter = self.nautobot_adapter()
        adapter.load()
        self.assertEqual(addresses_of(adapter, "ours", "eth0"), {"10.0.0.1": 24})

    def test_without_a_choice_every_address_is_loaded(self):
        self.interface.ip_addresses.add(make_address("10.0.0.1/24", self.namespace, self.active_status))
        self.interface.ip_addresses.add(make_address("10.0.0.2/24", get_default_namespace(), self.active_status))
        adapter = self.nautobot_adapter()
        adapter.load()
        self.assertEqual(addresses_of(adapter, "ours", "eth0"), {"10.0.0.1": 24, "10.0.0.2": 24})

    def test_only_its_prefixes_and_vrfs_are_loaded(self):
        for namespace in (self.namespace, get_default_namespace()):
            VRF.objects.create(name=namespace.name, namespace=namespace, status=self.active_status)
        nbutils.use_namespace(self.namespace)
        adapter = self.nautobot_adapter()
        nbutils.create_prefix("10.1.0.0/24")
        Prefix.objects.create(
            prefix="10.2.0.0/24", namespace=get_default_namespace(), status=self.active_status
        ).tags.add(adapter.ssot_tag)
        adapter.load()
        self.assertEqual([vrf.name for vrf in adapter.get_all("vrf")], ["customer-a"])
        self.assertEqual([prefix.prefix for prefix in adapter.get_all("prefix")], ["10.1.0.0/24"])

    def test_only_its_address_is_updated_on_an_interface(self):
        in_global = make_address("10.0.0.1/24", get_default_namespace(), self.active_status)
        ours = make_address("10.0.0.1/24", self.namespace, self.active_status)
        self.interface.ip_addresses.add(in_global, ours)
        nbutils.use_namespace(self.namespace)
        model = diffsync_models.InterfaceAddress(
            adapter=self.nautobot_adapter(), device_name="ours", interface_name="eth0", host="10.0.0.1", mask_length=24
        )
        self.assertIsNotNone(model.update({"is_primary": True}))
        self.assertEqual(Device.objects.get(name="ours").primary_ip4, ours)

    def test_only_its_address_is_deleted_from_an_interface(self):
        in_global = make_address("10.0.0.1/24", get_default_namespace(), self.active_status)
        ours = make_address("10.0.0.1/24", self.namespace, self.active_status)
        self.interface.ip_addresses.add(in_global, ours)
        nbutils.use_namespace(self.namespace)
        adapter = self.nautobot_adapter(safe_delete_mode=False)
        diffsync_models.InterfaceAddress(
            adapter=adapter, device_name="ours", interface_name="eth0", host="10.0.0.1", mask_length=24
        ).delete()
        self.assertEqual(adapter.objects_to_delete["_ipaddress"], [(IPAddress, ours.pk)])
