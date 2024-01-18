"""Unit tests for the Infoblox DiffSync adapter class."""
import json
import unittest

from django.test import TestCase
from nautobot.extras.models import JobResult
from diffsync.exceptions import ObjectNotFound

from nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox import (
    InfobloxAdapter,
    PLUGIN_CFG,
)
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
        self.conn = unittest.mock.MagicMock()

        self.job = InfobloxDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.infoblox = InfobloxAdapter(job=self.job, sync=None, conn=self.conn)
        return super().setUp()

    @unittest.mock.patch(
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

    @unittest.mock.patch(
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


class TestInfobloxAdapter(unittest.TestCase):
    """Test cases for InfobloxAdapter."""

    def setUp(self):
        with unittest.mock.patch(
            "nautobot_ssot.integrations.infoblox.utils.client.InfobloxApi", autospec=True
        ) as mock_client:
            self.infoblox_adapter = InfobloxAdapter(
                job=unittest.mock.Mock(),
                sync=unittest.mock.Mock(),
                conn=mock_client,
            )

    @unittest.mock.patch.dict(PLUGIN_CFG, [("infoblox_import_subnets", [])])
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={"attr1": "data"},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {"attr2": "value"}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
        side_effect=[{10: {"vid": 10, "name": "ten", "group": "group_a"}}],
    )
    def test_load_prefixes_no_infoblox_import_subnets(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        self.infoblox_adapter.conn.get_network_containers.return_value = [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/8/default",
                "comment": "root",
                "extattrs": {},
                "network": "10.0.0.0/8",
                "network_view": "default",
                "rir": "NONE",
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDE5Mi4xNjguMi4wLzI0LzA:10.0.0.0/16/default",
                "comment": "",
                "extattrs": {},
                "network": "10.0.0.0/16",
                "network_view": "default",
                "rir": "NONE",
            },
        ]
        self.infoblox_adapter.conn.get_all_subnets.return_value = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {"attr2": "value"},  # this is mocked out, but also present for clearer reading
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [10],
                "ranges": ["10.0.0.150-10.0.0.254", "10.0.1.150-.10.0.1.254"],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIwLjY0LjAvMjEvMA:10.0.100.0/24/default",
                "extattrs": {},
                "network": "10.0.100.0/24",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
        ]
        self.infoblox_adapter.load_prefixes()
        self.infoblox_adapter.conn.get_tree_from_container.assert_not_called()
        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 4)
        mock_build_vlan_map.assert_called_once()
        self.assertEqual(len(self.infoblox_adapter.get_all("prefix")), 4)
        subnet_with_attrs = self.infoblox_adapter.get("prefix", "10.0.0.0/23")
        self.assertEqual(subnet_with_attrs.ext_attrs, {"attr1": "data", "attr2": "value"})
        self.assertEqual(subnet_with_attrs.vlans, {10: {"vid": 10, "name": "ten", "group": "group_a"}})
        self.assertEqual(subnet_with_attrs.ranges, ["10.0.0.150-10.0.0.254", "10.0.1.150-.10.0.1.254"])
        subnet_without_attrs = self.infoblox_adapter.get("prefix", "10.0.100.0/24")
        self.assertEqual(subnet_without_attrs.ext_attrs, {"attr1": "data"})
        self.assertEqual(subnet_without_attrs.vlans, {})
        self.assertEqual(subnet_without_attrs.ranges, [])

    @unittest.mock.patch.dict(PLUGIN_CFG, [("infoblox_import_subnets", ["10.0.0.0/8", "192.168.0.0/16"])])
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}, {}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
    )
    def test_load_prefixes_with_infoblox_import_subnets(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        ten_container = [
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDEwLjAuMC4wLzgvMA:10.0.0.0/8/default",
                "extattrs": {},
                "network": "10.0.0.0/8",
                "network_view": "default",
                "rir": "NONE",
                "status": "container",
            },
            {
                "_ref": "networkcontainer/ZG5zLm5ldHdvcmtfY29udGFpbmVyJDEwLjAuMC4wLzgvMA:10.0.0.0/16/default",
                "extattrs": {},
                "network": "10.0.0.0/16",
                "network_view": "default",
                "rir": "NONE",
                "status": "container",
            },
        ]
        self.infoblox_adapter.conn.get_tree_from_container.side_effect = [ten_container, []]
        ten_network = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuNTguMTI4LjAvMTgvMA:10.0.1.0/23/default",
                "extattrs": {},
                "network": "10.0.1.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
        ]
        self.infoblox_adapter.conn.get_child_subnets_from_container.side_effect = [
            [],
            ten_network,
        ]
        one_nine_two_network = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuNTguMTI4LjAvMTgvMA:192.168.0.0/23/default",
                "extattrs": {},
                "network": "192.168.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
            },
        ]
        self.infoblox_adapter.conn.get_all_subnets.side_effect = [one_nine_two_network]
        self.infoblox_adapter.conn.remove_duplicates.side_effect = [ten_network + one_nine_two_network, ten_container]
        self.infoblox_adapter.load_prefixes()
        self.infoblox_adapter.conn.get_tree_from_container.assert_has_calls(
            [unittest.mock.call("10.0.0.0/8"), unittest.mock.call("192.168.0.0/16")]
        )
        self.assertEqual(self.infoblox_adapter.conn.get_tree_from_container.call_count, 2)
        self.infoblox_adapter.conn.get_child_subnets_from_container.assert_has_calls(
            [unittest.mock.call(prefix="10.0.0.0/8"), unittest.mock.call(prefix="10.0.0.0/16")]
        )
        self.assertEqual(self.infoblox_adapter.conn.get_child_subnets_from_container.call_count, 2)
        self.infoblox_adapter.conn.get_all_subnets.assert_called_once()
        self.infoblox_adapter.conn.get_all_subnets.assert_called_with("192.168.0.0/16")
        self.assertEqual(self.infoblox_adapter.conn.remove_duplicates.call_count, 2)
        mock_default_extra_attrs.assert_called_once()
        self.assertEqual(mock_extra_attr_dict.call_count, 4)
        mock_build_vlan_map.assert_not_called()
        self.assertEqual(len(self.infoblox_adapter.get_all("prefix")), 4)

    @unittest.mock.patch.dict(PLUGIN_CFG, [("infoblox_import_subnets", [])])
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_default_ext_attrs",
        autospec=True,
        return_value={},
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.get_ext_attr_dict",
        autospec=True,
        side_effect=[{}, {}],
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.infoblox.diffsync.adapters.infoblox.build_vlan_map",
        autospec=True,
    )
    def test_load_prefixes_add_duplicate_prefix(
        self,
        mock_build_vlan_map,
        mock_extra_attr_dict,
        mock_default_extra_attrs,
    ):
        self.infoblox_adapter.conn.get_network_containers.return_value = []
        self.infoblox_adapter.conn.get_all_subnets.return_value = [
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {},
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
            {
                "_ref": "network/ZG5zLm5ldHdvcmskMTAuMjIzLjAuMC8yMS8w:10.0.0.0/23/default",
                "extattrs": {},
                "network": "10.0.0.0/23",
                "network_view": "default",
                "rir": "NONE",
                "vlans": [],
                "ranges": [],
            },
        ]
        error_message = (
            "Duplicate prefix found: 10.0.0.0/23. Duplicate prefixes are not supported, "
            "and only the first occurrence will be included in the sync. To load data "
            "from a single Network View, use the 'infoblox_network_view' setting."
        )
        self.infoblox_adapter.load_prefixes()
        self.infoblox_adapter.job.logger.warning.assert_called_once()
        self.infoblox_adapter.job.logger.warning.assert_called_with(error_message)
        mock_build_vlan_map.assert_not_called()
        self.assertEqual(mock_extra_attr_dict.call_count, 2)
        mock_default_extra_attrs.assert_called_once()
