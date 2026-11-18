"""Unit tests for the Slurpit DiffSync adapter class."""

import ipaddress
import json
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, create_autospec

from nautobot.dcim.models import LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import JobResult
from nautobot.ipam.models import Namespace
from slurpit.apis.planningapi import PlanningAPI
from slurpit.models.device import Device
from slurpit.models.planning import Planning
from slurpit.models.site import Site
from slurpit.utils.utils import handle_response_data

from nautobot_ssot.integrations.slurpit import constants
from nautobot_ssot.integrations.slurpit.diffsync.adapters.slurpit import SlurpitAdapter
from nautobot_ssot.integrations.slurpit.jobs import SlurpitDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


SITE_FIXTURE = handle_response_data(load_json("./nautobot_ssot/tests/slurpit/fixtures/sites.json"), object_class=Site)
DEVICE_FIXTURE = handle_response_data(
    load_json("./nautobot_ssot/tests/slurpit/fixtures/devices.json"), object_class=Device
)
PLANNING_FIXTURE = handle_response_data(
    load_json("./nautobot_ssot/tests/slurpit/fixtures/plannings.json"), object_class=Planning
)
INVENTORY_ITEM_FIXTURE = load_json("./nautobot_ssot/tests/slurpit/fixtures/inventory_items.json")
VLANS_FIXTURE = load_json("./nautobot_ssot/tests/slurpit/fixtures/vlans.json")
ROUTING_TABLE_FIXTURE = load_json("./nautobot_ssot/tests/slurpit/fixtures/routing_table.json")
INTERFACES_FIXTURE = load_json("./nautobot_ssot/tests/slurpit/fixtures/interfaces.json")


class SlurpitDiffSyncTestCase(TestCase):
    """Test the SlurpitDiffSync adapter class."""

    def setUp(self):
        populate_status_choices()
        slurpit_client = AsyncMock()
        slurpit_client.site.get_sites = AsyncMock(return_value=SITE_FIXTURE)
        slurpit_client.device.get_devices = AsyncMock(return_value=DEVICE_FIXTURE)
        slurpit_client.planning.get_plannings = AsyncMock(return_value=PLANNING_FIXTURE)

        job = SlurpitDataSource()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        job.site_loctype = LocationType.objects.get_or_create(name="Site")[0]
        job.namespace = Namespace.objects.get_or_create(name="Global")[0]
        self.slurpit = SlurpitAdapter(job=job, api_client=slurpit_client)

        def site_effect(value):
            return {
                "hardware-info": INVENTORY_ITEM_FIXTURE,
                "vlans": VLANS_FIXTURE,
                "routing-table": ROUTING_TABLE_FIXTURE,
                "interfaces": INTERFACES_FIXTURE,
            }.get(value, [])

        self.slurpit.planning_results = MagicMock(return_value=PLANNING_FIXTURE, side_effect=site_effect)
        self.slurpit.load()

    def test_loading_data(self):
        """Test the load() function."""
        print(self.slurpit.get_all("location"))
        self.assertEqual(
            {site.sitename for site in SITE_FIXTURE},
            {site.name for site in self.slurpit.get_all("location")},
        )

        self.assertEqual(
            {brand["brand"] for brand in self.slurpit.unique_vendors()},
            {vendor.name for vendor in self.slurpit.get_all("manufacturer")},
        )

        self.assertEqual(
            {device_type["device_type"] for device_type in self.slurpit.unique_device_type()},
            {device_type.model for device_type in self.slurpit.get_all("device_type")},
        )

        self.assertEqual(
            set(self.slurpit.unique_platforms()),
            {platform.name for platform in self.slurpit.get_all("platform")},
        )

        self.assertEqual(constants.DEFAULT_DEVICE_ROLE, self.slurpit.get_all("role")[0].name)

        self.assertEqual(
            {device.hostname for device in DEVICE_FIXTURE},
            {device.name for device in self.slurpit.get_all("device")},
        )

        inventory_item_names = [
            inventory_item.get("Name") or inventory_item.get("Product")
            for inventory_item in self.slurpit.planning_results("hardware-info")
        ]

        self.assertEqual(
            set(inventory_item_names),
            {inventory_item.name for inventory_item in self.slurpit.get_all("inventory_item")},
        )

        self.assertEqual(
            {vlan["Name"] for vlan in self.slurpit.planning_results("vlans")},
            {vlan.name for vlan in self.slurpit.get_all("vlan")},
        )

        vrfs = {vrf["Vrf"] for vrf in self.slurpit.planning_results("routing-table") if vrf.get("Vrf", "")}

        self.assertEqual(
            vrfs,
            {vrf.name for vrf in self.slurpit.get_all("vrf")},
        )

        self.assertEqual(
            {
                prefix["normalized_prefix"].split("/")[0]
                for prefix in load_json("./nautobot_ssot/tests/slurpit/fixtures/prefixes.json")
            },
            {prefix.network for prefix in self.slurpit.get_all("prefix")},
        )

        interfaces = self.slurpit.planning_results("interfaces")

        self.assertEqual(
            {
                ip["normalized_address"].split("/")[0]
                for ip in self.slurpit.run_async(self.slurpit.filter_interfaces(interfaces))
            },
            {ip.host for ip in self.slurpit.get_all("ipaddress")},
        )

        self.assertEqual(
            {interface["Interface"] for interface in self.slurpit.planning_results("interfaces")},
            {interface.name for interface in self.slurpit.get_all("interface")},
        )

    def test_primary_ip_from_device_address(self):
        """Test the device `address` field is used to set the primary IP of the device."""
        self.assertEqual(
            {device.hostname: ipaddress.ip_address(device.address) for device in DEVICE_FIXTURE if device.address},
            self.slurpit.hostname_to_primary_ip,
        )
        assignment = self.slurpit.get(
            "ipassignment",
            {
                "interface__device__name": "sandbox-xr",
                "interface__name": "MgmtEth0/RP0/CPU0/0",
                "ip_address__host": "10.10.20.175",
            },
        )
        self.assertEqual("10.10.20.175", assignment.interface__device__primary_ip4__host)
        self.assertIsNone(assignment.interface__device__primary_ip6__host)


class SlurpitAdapterHelpersTestCase(TestCase):
    """Test the SlurpitAdapter helpers that call the Slurpit SDK without loading data into Nautobot."""

    def setUp(self):
        # Autospec the SDK API classes so calls with arguments the installed SDK doesn't accept fail the test.
        slurpit_client = MagicMock()
        slurpit_client.planning = create_autospec(PlanningAPI, instance=True)
        slurpit_client.planning.get_plannings.return_value = PLANNING_FIXTURE
        slurpit_client.planning.search_plannings.return_value = INTERFACES_FIXTURE
        self.client = slurpit_client
        self.slurpit = SlurpitAdapter(job=MagicMock(), api_client=slurpit_client)

    def test_planning_results(self):
        """Test planning_results() searches the planning matching the slug."""
        planning = next(plan for plan in PLANNING_FIXTURE if plan.slug == "interfaces")

        self.assertEqual(INTERFACES_FIXTURE, self.slurpit.planning_results("interfaces"))
        self.client.planning.search_plannings.assert_awaited_once_with(
            {"planning_id": planning.id, "unique_results": True, "latest": True}, limit=30000
        )

    def test_planning_results_unknown_planning(self):
        """Test planning_results() raises IndexError when no planning matches the slug."""
        with self.assertRaises(IndexError):
            self.slurpit.planning_results("does-not-exist")
        self.client.planning.search_plannings.assert_not_awaited()

    def test_planning_results_empty(self):
        """Test planning_results() returns an empty list when the search has no results."""
        self.client.planning.search_plannings.return_value = []
        self.assertEqual([], self.slurpit.planning_results("interfaces"))

    def test_device_accepts_current_api_payload(self):
        """Test the SDK Device model accepts the device payload returned by current Slurpit servers."""
        payload = load_json("./nautobot_ssot/tests/slurpit/fixtures/devices.json")[0]
        payload["new_field_from_newer_server"] = "value"
        device = Device(**payload)
        self.assertEqual("10.10.20.175", device.address)
        self.assertEqual("IPv4", device.family)

    def test_get_primary_ip(self):
        """Test _get_primary_ip() handles IPv4, IPv6, prefix notation and missing or invalid addresses."""
        cases = {
            "10.10.20.175": ipaddress.ip_address("10.10.20.175"),
            "10.10.20.175/24": ipaddress.ip_address("10.10.20.175"),
            "2001:db8::1": ipaddress.ip_address("2001:db8::1"),
            "": None,
            None: None,
            "not-an-ip": None,
        }
        for address, expected in cases.items():
            with self.subTest(address=address):
                self.assertEqual(expected, SlurpitAdapter._get_primary_ip(MagicMock(address=address)))  # pylint: disable=protected-access
