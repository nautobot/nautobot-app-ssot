"""Tests for naming the Devices of a stack, and renaming them when the format changes."""

from unittest.mock import MagicMock, patch

from django.apps import apps as global_apps
from django.test import SimpleTestCase
from nautobot.dcim.models import Device
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.signals import nautobot_database_ready_callback
from nautobot_ssot.integrations.ipfabric.sync_scope import SyncScope
from nautobot_ssot.integrations.ipfabric.utilities.utils import check_stack_name_formats, stack_device_name
from nautobot_ssot.tests.ipfabric.job_log import job_log_text
from nautobot_ssot.tests.ipfabric.supporting_objects import SupportingObjectTestCase
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import INTERFACE_FIXTURE, build_adapter, mock_ipfabric_client

ADAPTER = "nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric"


class StackNameFormatTestCase(SimpleTestCase):
    """Checking and applying the formats stack Devices are named by."""

    def test_the_defaults_and_a_padded_format_are_accepted(self):
        check_stack_name_formats("{hostname}-member{member}", "{hostname}")
        check_stack_name_formats("{hostname}-{member:02d}", "{hostname}-{member:02d}")

    def test_an_unusable_format_is_refused_naming_the_setting(self):
        for member_format, master_format, setting in (
            ("{hostname}-{serial}", "{hostname}", "ipfabric_stack_member_name"),
            ("{hostname}-{member}", "{hostname.upper}", "ipfabric_stack_master_name"),
            ("{hostname}-{member:zz}", "{hostname}", "ipfabric_stack_member_name"),
            ("{hostname}-{member", "{hostname}", "ipfabric_stack_member_name"),
            ("{hostname}-stack", "{hostname}", "ipfabric_stack_member_name"),
        ):
            with self.subTest(member_format=member_format, master_format=master_format):
                with self.assertRaisesRegex(ValueError, setting):
                    check_stack_name_formats(member_format, master_format)

    def test_a_member_number_ip_fabric_reports_as_a_string_is_padded(self):
        self.assertEqual(stack_device_name("{hostname}-{member:02d}", "HWLAB-C3750-STACK", "2"), "HWLAB-C3750-STACK-02")


class IPFabricStackNameTestCase(SupportingObjectTestCase):
    """Naming a stack's Devices, and finding the master by its new name everywhere else."""

    def names(self, adapter):
        """Return the names of the stack's Devices the adapter loaded."""
        return sorted(device.name for device in adapter.get_all("device") if device.vc_name == "stack")

    def test_the_default_formats_keep_todays_names(self):
        adapter = build_adapter()
        self.assertEqual(self.names(adapter), ["stack", "stack-member2", "stack-member4"])
        self.assertEqual(adapter.device_names, {})

    def test_members_and_the_master_take_the_configured_formats(self):
        with patch.dict(
            f"{ADAPTER}.__dict__",
            {"STACK_MEMBER_NAME": "{hostname}-{member:02d}", "STACK_MASTER_NAME": "{hostname}-{member:02d}"},
        ):
            adapter = build_adapter()
        self.assertEqual(self.names(adapter), ["stack-01", "stack-02", "stack-04"])
        self.assertEqual(adapter.device_names, {"stack": "stack-01"})
        self.assertEqual(adapter.stack_device_names["stack"], {1: "stack-01", 2: "stack-02", 4: "stack-04"})

    def test_the_masters_interfaces_links_and_vrfs_follow_its_new_name(self):
        client = mock_ipfabric_client()
        stack_interface = {**INTERFACE_FIXTURE[0], "hostname": "stack", "sn": "stack1", "intName": "Gi1/0/1"}
        client.inventory.interfaces.all.return_value = [*INTERFACE_FIXTURE, stack_interface]
        with patch.dict(f"{ADAPTER}.__dict__", {"STACK_MASTER_NAME": "{hostname}-{member:02d}"}):
            adapter = build_adapter(client=client)
        # Reported against the stack's hostname, and found under the master's new name.
        self.assertEqual(
            {model.device_name for model in adapter.get_all("interface") if model.device_name.startswith("stack")},
            {"stack-01"},
        )
        self.assertEqual(adapter.link_endpoint({"localHost": "stack", "localInt": "Gi1/0/1"}, "local")[0], "stack-01")
        adapter.load_vrf_device_assignments([{"vrf": "BLUE", "hostname": "stack"}])
        self.assertEqual([model.device_name for model in adapter.get_all("vrf_device_assignment")], ["stack-01"])

    def test_an_unusable_format_stops_the_load(self):
        with patch.dict(f"{ADAPTER}.__dict__", {"STACK_MEMBER_NAME": "{hostname}"}):
            with self.assertRaisesRegex(ValueError, "ipfabric_stack_member_name"):
                build_adapter()


class RenameStackDevicesTestCase(SupportingObjectTestCase):
    """Renaming the stack Devices the sync wrote before the Nautobot side loads them."""

    def setUp(self):
        super().setUp()
        nautobot_database_ready_callback(sender=None, apps=global_apps)
        self.adapter.tenant = None
        self.adapter.sync_ipfabric_tagged_only = False
        self.create_device(name="stack", vc_name="stack", vc_master=True, vc_position=1, vc_priority=1)
        self.create_device(name="stack-member2", vc_name="stack", vc_master=False, vc_position=2, vc_priority=2)

    def rename(self, dryrun=False, tenant=None, names=None):
        """Run the rename for the stack named "stack", returning the adapter's job."""
        job = MagicMock(dryrun=dryrun)
        adapter = NautobotDiffSync(
            job=job,
            sync=None,
            sync_ipfabric_tagged_only=False,
            location_filter=None,
            scope=SyncScope([]),
            tenant=tenant,
            stack_device_names={"stack": names or {1: "stack-01", 2: "stack-02"}},
        )
        adapter.rename_stack_devices()
        return job

    def names(self):
        """Return the names of the stack's Devices in Nautobot."""
        return sorted(Device.objects.filter(virtual_chassis__name="stack").values_list("name", flat=True))

    def test_the_stack_is_renamed_by_position_and_reported(self):
        job = self.rename()
        self.assertEqual(self.names(), ["stack-01", "stack-02"])
        self.assertIn("Renamed 2 stack Devices to the configured format", job_log_text(job.logger, "info"))

    def test_a_device_already_named_so_is_left_alone(self):
        job = self.rename(names={1: "stack", 2: "stack-member2"})
        self.assertEqual(self.names(), ["stack", "stack-member2"])
        self.assertEqual(job_log_text(job.logger, "info"), "")

    def test_a_dry_run_only_reports_the_renames(self):
        job = self.rename(dryrun=True)
        self.assertEqual(self.names(), ["stack", "stack-member2"])
        self.assertIn("would rename 2 stack Devices", job_log_text(job.logger, "info"))

    def test_a_device_the_sync_never_tagged_is_not_renamed(self):
        Device.objects.get(name="stack-member2").tags.clear()
        self.rename()
        self.assertEqual(self.names(), ["stack-01", "stack-member2"])

    def test_only_the_tenants_devices_are_renamed(self):
        self.rename(tenant=Tenant.objects.create(name="customer-a"))
        self.assertEqual(self.names(), ["stack", "stack-member2"])

    def test_a_name_another_device_holds_is_reported(self):
        self.create_device(name="stack-02")
        job = self.rename()
        self.assertIn("stack-01", self.names())
        self.assertIn("stack-member2", self.names())
        self.assertIn("Unable to rename the stack Device stack-member2 to stack-02", job_log_text(job.logger, "error"))
