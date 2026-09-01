"""Test that a second sync of unchanged data reports nothing to do.

A sync that keeps reporting the same change every run is as much a defect as one that fails: it
writes to the change log forever, and it hides the changes that matter. Neither adapter's tests can
catch it, because it comes from the two disagreeing about how to describe the same object.

The check is the whole point here: sync once into an empty Nautobot, load Nautobot again, and diff
against the same source. Anything the second diff reports is a disagreement, and the attribute it
names is the one to look at.
"""

import json
import unittest.mock
from collections import defaultdict

from diffsync.enum import DiffSyncFlags
from ipfabric.models.device import Device as IPFDevice
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Interface
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import JobResult, Status
from nautobot.ipam.choices import PrefixTypeChoices
from nautobot.ipam.models import IPAddress, Prefix, get_default_namespace

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.jobs import IpFabricDataSource
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache

FIXTURES = "./nautobot_ssot/tests/ipfabric/fixtures"


def load_json(path):
    """Load a json fixture."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


class SyncConvergenceTestCase(TestCase):
    """Sync the fixtures in twice and require the second run to find nothing to change."""

    databases = ("default", "job_logs")

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.sites = load_json(f"{FIXTURES}/get_sites.json")
        self.devices = load_json(f"{FIXTURES}/get_device_inventory.json")
        self.vlans = load_json(f"{FIXTURES}/get_vlans.json")
        self.interfaces = load_json(f"{FIXTURES}/get_interface_inventory.json")
        self.stacks = load_json(f"{FIXTURES}/get_stack_members.json")
        # The addresses IP Fabric reports for the interfaces above, with the subnet each sits in.
        self.networks = [
            {"net": "10.10.0.0/24", "sn": "a000a02", "ip": "10.10.0.10"},
            {"net": "10.11.0.0/25", "sn": "a000a01", "ip": "10.11.0.10"},
        ]

    def ipf_client(self):
        """Return a mock IPFClient serving the fixtures."""
        client = unittest.mock.MagicMock()
        client.inventory.sites.all.return_value = self.sites
        client.devices.by_site = defaultdict(list)
        for device in self.devices:
            client.devices.by_site[device["siteName"]].append(IPFDevice(**device))  # pylint: disable=no-member
        client.fetch_all = unittest.mock.MagicMock(
            side_effect=(lambda table: self.vlans if table == "tables/vlan/site-summary" else "")
        )
        client.inventory.interfaces.all.return_value = self.interfaces
        client.technology.addressing.managed_ip_ipv4.all.return_value = self.networks
        client.technology.platforms.stacks_members.all.return_value = self.stacks
        client.technology.interfaces.connectivity_matrix.all.return_value = []
        return client

    def job(self):
        """Return a job with a real JobResult, since the adapters log through it."""
        job = IpFabricDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="convergence", worker="default")
        job.logger = unittest.mock.MagicMock()
        job.debug = False
        return job

    def source(self, job, scope):
        """Return a loaded IP Fabric adapter."""
        adapter = IPFabricDiffSync(job=job, sync=None, client=self.ipf_client(), location_filter=None, scope=scope)
        adapter.load()
        return adapter

    def destination(self, job, scope, bulk_write_mode=False):
        """Return a loaded Nautobot adapter."""
        adapter = NautobotDiffSync(
            job=job,
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            bulk_write_mode=bulk_write_mode,
            scope=scope,
        )
        adapter.load()
        return adapter

    def sync_once(self, bulk_write_mode=False):
        """Sync the fixtures into Nautobot, and return the summary of what it did."""
        job = self.job()
        scope = SyncScope.from_job_kwargs({})
        source = self.source(job, scope)
        destination = self.destination(job, scope, bulk_write_mode=bulk_write_mode)
        destination.sync_from(source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
        return job

    def remaining_diff(self):
        """Return the summary of a diff taken against a freshly loaded Nautobot."""
        job = self.job()
        scope = SyncScope.from_job_kwargs({})
        source = self.source(job, scope)
        destination = self.destination(job, scope)
        return destination.diff_from(source)

    def changed_attributes(self, diff):
        """Return the attribute names the diff reports as changing, by model."""
        changed = defaultdict(set)
        for element in diff.get_children():
            self.collect(element, changed)
        return {model: sorted(names) for model, names in changed.items() if names}

    def collect(self, element, changed):
        """Walk a diff element and its children, recording the attributes reported as changed."""
        for attrs in element.get_attrs_diffs().values():
            if isinstance(attrs, dict):
                changed[element.type].update(attrs)
        for child in element.get_children():
            self.collect(child, changed)

    def address_state(self):
        """Return every address on every Interface, as `device:interface -> [address, ...]`."""
        state = defaultdict(list)
        for interface in Interface.objects.all().prefetch_related("ip_addresses"):
            for address in interface.ip_addresses.all():
                state[f"{interface.device.name}:{interface.name}"].append(str(address.address))
        return {key: sorted(value) for key, value in state.items()}

    def test_a_second_sync_of_unchanged_data_reports_nothing(self):
        """Anything reported here is the two adapters describing one object differently."""
        self.sync_once()

        diff = self.remaining_diff()

        self.assertEqual(
            self.changed_attributes(diff),
            {},
            f"Second sync still reports changes: {diff.str()}",
        )

    def test_a_second_sync_reports_nothing_in_bulk_write_mode_either(self):
        """The batched path has to land the same values the per-object one does."""
        self.sync_once(bulk_write_mode=True)

        diff = self.remaining_diff()

        self.assertEqual(
            self.changed_attributes(diff),
            {},
            f"Second sync after a bulk write still reports changes: {diff.str()}",
        )

    def test_a_second_sync_reports_nothing_when_nautobot_held_another_mask(self):
        """The situation a real estate is in: the address exists, under a mask of its own.

        IP Fabric reports the subnet an address sits in, and Nautobot reports the mask on the address
        row, so the two disagree until one of them is written.
        """
        prefix, _ = Prefix.objects.get_or_create(
            prefix="10.10.0.0/16",
            namespace=get_default_namespace(),
            defaults={"status": Status.objects.get(name="Active"), "type": PrefixTypeChoices.TYPE_NETWORK},
        )
        held = IPAddress(address="10.10.0.10/16", parent=prefix, status=Status.objects.get(name="Active"))
        held.validated_save()

        self.sync_once()
        diff = self.remaining_diff()

        self.assertEqual(
            self.changed_attributes(diff),
            {},
            f"Second sync still reports changes: {diff.str()}",
        )

    def test_an_interface_reports_one_address_after_a_sync(self):
        """Nautobot reports whichever address comes back first, so a second one makes the diff flap."""
        self.sync_once()

        addressed = {key: value for key, value in self.address_state().items() if value}

        self.assertTrue(addressed, "Expected the fixtures to put an address on at least one Interface.")
        for interface, addresses in addressed.items():
            self.assertEqual(len(addresses), 1, f"{interface} holds {addresses}")
