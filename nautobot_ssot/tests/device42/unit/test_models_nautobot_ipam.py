"""Test DiffSync IPAM models for Nautobot."""
from unittest.mock import MagicMock, patch
from diffsync import DiffSync
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import Status
from nautobot.ipam.models import Namespace, Prefix, VRF
from nautobot_ssot.integrations.device42.diffsync.models.nautobot import ipam


class TestNautobotVRFGroup(TransactionTestCase):
    """Test the NautobotVRFGroup class."""

    def setUp(self):
        self.diffsync = DiffSync()
        self.diffsync.namespace_map = {}
        self.diffsync.vrf_map = {}
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()
        self.vrf = VRF.objects.create(name="Test")
        self.vrf.validated_save()

    def test_create(self):
        """Validate the NautobotVRFGroup create() method creates a VRF."""
        self.vrf.delete()
        ids = {"name": "Test"}
        attrs = {"description": "Test VRF", "tags": ["test"], "custom_fields": {}}
        result = ipam.NautobotVRFGroup.create(self.diffsync, ids, attrs)
        self.assertIsInstance(result, ipam.NautobotVRFGroup)
        self.diffsync.job.logger.info.assert_called_once_with("Creating VRF Test.")
        namespace = Namespace.objects.get(name=ids["name"])
        self.assertEqual(namespace.name, ids["name"])
        self.assertEqual(self.diffsync.namespace_map[ids["name"]], namespace.id)
        vrf = VRF.objects.get(name=ids["name"])
        self.assertEqual(self.diffsync.vrf_map[ids["name"]], vrf.id)
        self.assertEqual(vrf.namespace.name, ids["name"])

    def test_update(self):
        """Validate the NautobotVRFGroup update() updates a VRF."""
        test_vrf = ipam.NautobotVRFGroup(
            name="Test", description="Test VRF", tags=["test"], custom_fields={}, uuid=self.vrf.id
        )
        test_vrf.diffsync = self.diffsync
        update_attrs = {"description": "Test VRF Update", "custom_fields": {"test": {"key": "test", "value": "test"}}}
        actual = ipam.NautobotVRFGroup.update(self=test_vrf, attrs=update_attrs)
        self.diffsync.job.logger.info.assert_called_once_with("Updating VRF Test.")
        self.vrf.refresh_from_db()
        self.assertEqual(self.vrf.description, update_attrs["description"])
        self.assertEqual(self.vrf.custom_field_data["test"], "test")
        self.assertEqual(actual, test_vrf)
        self.assertEqual(self.vrf.description, "Test VRF Update")
        self.assertEqual(self.vrf.custom_field_data["test"], "test")

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.PLUGIN_CFG",
        {"device42_delete_on_sync": True},
    )
    @patch("nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.OrmVRF.objects.get")
    def test_delete(self, mock_vrf):
        """Validate the NautobotVRFGroup delete() deletes a VRF."""
        vrf_group = ipam.NautobotVRFGroup(
            name="Test", description=None, tags=None, custom_fields=None, uuid=self.vrf.id
        )
        vrf_group.diffsync = self.diffsync
        mock_vrf.return_value = self.vrf
        self.diffsync.objects_to_delete = {"vrf": []}

        vrf_group.delete()

        self.diffsync.job.logger.info.assert_called_once_with("VRF Test will be deleted.")
        self.assertEqual(len(self.diffsync.objects_to_delete["vrf"]), 1)
        self.assertEqual(self.diffsync.objects_to_delete["vrf"][0].id, self.vrf.id)


class TestNautobotSubnet(TransactionTestCase):
    """Test the NautobotSubnet class."""

    def setUp(self):
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        self.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        self.test_vrf = VRF.objects.get_or_create(name="Test", namespace=self.test_ns)[0]
        self.prefix = Prefix.objects.create(prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active)
        self.diffsync = DiffSync()
        self.diffsync.namespace_map = {"Test": self.test_ns.id}
        self.diffsync.vrf_map = {"Test": self.test_vrf.id}
        self.diffsync.status_map = {"Active": self.status_active.id}
        self.diffsync.prefix_map = {}
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()

    def test_create(self):
        """Validate the NautobotSubnet create() method creates a Prefix."""
        self.prefix.delete()
        ids = {"network": "10.0.0.0", "mask_bits": "24", "vrf": "Test"}
        attrs = {"description": "", "tags": [], "custom_fields": {}}
        result = ipam.NautobotSubnet.create(self.diffsync, ids, attrs)
        self.assertIsInstance(result, ipam.NautobotSubnet)
        self.diffsync.job.logger.info.assert_called_once_with("Creating Prefix 10.0.0.0/24 in VRF Test.")
        subnet = Prefix.objects.get(prefix=f"{ids['network']}/{ids['mask_bits']}", namespace=self.test_ns)
        self.assertEqual(str(subnet.prefix), f"{ids['network']}/{ids['mask_bits']}")
        self.assertEqual(self.diffsync.prefix_map["Test"][f"{ids['network']}/{ids['mask_bits']}"], subnet.id)
        self.assertEqual(subnet.vrfs.all().first(), self.test_vrf)

    def test_update(self):
        """Validate the NautobotSubnet update() method updates a Prefix."""
        test_pf = ipam.NautobotSubnet(
            network="10.0.0.0",
            mask_bits=24,
            description=None,
            vrf="Test",
            tags=[],
            custom_fields={},
            uuid=self.prefix.id,
        )
        test_pf.diffsync = self.diffsync
        update_attrs = {
            "description": "Test Prefix",
            "tags": ["test"],
            "custom_fields": {"test": {"key": "test", "value": "test"}},
        }
        actual = ipam.NautobotSubnet.update(self=test_pf, attrs=update_attrs)
        self.diffsync.job.logger.info.assert_called_once_with("Updating Prefix 10.0.0.0/24.")
        self.prefix.refresh_from_db()
        self.assertEqual(self.prefix.description, "Test Prefix")
        self.assertEqual(actual, test_pf)

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.PLUGIN_CFG",
        {"device42_delete_on_sync": True},
    )
    @patch("nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.OrmPrefix.objects.get")
    def test_delete(self, mock_vrf):
        """Validate the NautobotVRFGroup delete() deletes a Prefix."""
        test_pf = ipam.NautobotSubnet(
            network="10.0.0.0",
            mask_bits=24,
            description=None,
            vrf="Test",
            tags=None,
            custom_fields=None,
            uuid=self.prefix.id,
        )
        test_pf.diffsync = self.diffsync
        mock_vrf.return_value = self.prefix
        self.diffsync.objects_to_delete = {"subnet": []}

        test_pf.delete()

        self.diffsync.job.logger.info.assert_called_once_with("Prefix 10.0.0.0/24 will be deleted.")
        self.assertEqual(len(self.diffsync.objects_to_delete["subnet"]), 1)
        self.assertEqual(self.diffsync.objects_to_delete["subnet"][0].id, self.prefix.id)
