"""Unit tests for the Slurpit DiffSync adapter class."""

import json
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock

from nautobot.dcim.models import LocationType
from nautobot.extras.models import JobResult
from nautobot.ipam.models import Namespace
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
