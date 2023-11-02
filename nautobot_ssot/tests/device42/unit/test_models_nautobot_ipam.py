"""Test DiffSync IPAM models for Nautobot."""
from unittest.mock import MagicMock, patch
from diffsync import DiffSync
from nautobot.core.testing import TransactionTestCase
from nautobot.ipam.models import Namespace, VRF
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
        test_vrf.diffsync = MagicMock()
        test_vrf.diffsync.job.logger.info = MagicMock()
        update_attrs = {"description": "Test VRF Update", "custom_fields": {"test": {"key": "test", "value": "test"}}}
        actual = ipam.NautobotVRFGroup.update(self=test_vrf, attrs=update_attrs)
        test_vrf.diffsync.job.logger.info.assert_called_once_with("Updating VRF Test.")
        self.vrf.refresh_from_db()
        self.assertEqual(self.vrf.description, update_attrs["description"])
        self.assertEqual(self.vrf.custom_field_data["test"], "test")
        self.assertEqual(actual, test_vrf)

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
