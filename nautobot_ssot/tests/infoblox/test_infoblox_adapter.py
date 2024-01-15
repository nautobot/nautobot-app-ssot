"""Unit tests for the Infoblox DiffSync adapter class."""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase
from nautobot.extras.models import JobResult
from diffsync.exceptions import ObjectNotFound

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import InfobloxAdapter
from nautobot_ssot.integrations.infoblox.diffsync.models.infoblox import InfobloxNetwork
from nautobot_ssot.integrations.infoblox.jobs import InfobloxDataSource


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


CONTAINER_FIXTURE = load_json("./nautobot_ssot/tests/infoblox/fixtures/get_network_containers_list.json")
SUBNET_FIXTURE = load_json("./nautobot_ssot/tests/infoblox/fixtures/get_all_subnets_list.json")
IPV6_CONTAINER_FIXTURE = load_json("./nautobot_ssot/tests/infoblox/fixtures/get_network_containers_ipv6_list.json")


class InfobloxDiffSyncTestCase(TestCase):
    """Test the InfobloxDiffSync adapter class."""

    def setUp(self) -> None:
        # Create a mock client
        self.conn = MagicMock()

        self.job = InfobloxDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.infoblox = InfobloxAdapter(job=self.job, sync=None, conn=self.conn)
        return super().setUp()

    @patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.PLUGIN_CFG",
        {"infoblox_import_subnets": False, "infoblox_import_objects_subnets_ipv6": False},
    )
    def test_load_prefixes(self):
        """Test the load_prefixes function."""
        self.conn.get_all_subnets.return_value = SUBNET_FIXTURE
        self.conn.get_network_containers.return_value = CONTAINER_FIXTURE
        self.infoblox.load_prefixes()
        self.assertEqual(str(self.infoblox.get(InfobloxNetwork, {"network": "10.61.15.0/24"})), "10.61.15.0/24")
        with self.assertRaises(ObjectNotFound):
            self.infoblox.get(InfobloxNetwork, {"network": "2001:5b0:4100::/40"})

    @patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.PLUGIN_CFG",
        {"infoblox_import_subnets": False, "infoblox_import_objects_subnets_ipv6": True},
    )
    def test_load_prefixes_ipv6(self):
        """Test the load_prefixes function with IPv6 import set in nautobot_config."""

        def mock_get_network_containers(ipv6=False):
            if ipv6:
                return IPV6_CONTAINER_FIXTURE
            return CONTAINER_FIXTURE

        self.conn.get_network_containers.side_effect = mock_get_network_containers
        self.conn.get_all_subnets.return_value = SUBNET_FIXTURE
        self.infoblox.load_prefixes()
        self.assertEqual(str(self.infoblox.get(InfobloxNetwork, {"network": "10.61.15.0/24"})), "10.61.15.0/24")
        self.assertEqual(
            str(self.infoblox.get(InfobloxNetwork, {"network": "2001:5b0:4100::/40"})), "2001:5b0:4100::/40"
        )
