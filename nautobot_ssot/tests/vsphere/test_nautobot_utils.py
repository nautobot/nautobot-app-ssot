"""Unit tests for Nautobot Utility functions."""

import unittest

from django.contrib.contenttypes.models import ContentType
from nautobot.extras.models.statuses import Status
from nautobot.extras.models.tags import Tag
from nautobot.virtualization.models import Cluster, ClusterType, VirtualMachine

from nautobot_ssot.integrations.vsphere.utilities.nautobot_utils import (
    create_ssot_tag,
    tag_object,
)


class TestNautobotUtils(unittest.TestCase):
    """Test Nautobot Utility functions."""

    def setUp(self):
        test_cluster_type, _ = ClusterType.objects.get_or_create(name="Test")
        self.test_cluster, _ = Cluster.objects.get_or_create(
            name="Test Cluster", cluster_type=test_cluster_type
        )
        self.active_status, _ = Status.objects.get_or_create(name="Active")
        for model in [
            VirtualMachine,
        ]:
            self.active_status.content_types.add(
                ContentType.objects.get_for_model(model)
            )
            self.active_status.validated_save()

    def test_create_ssot_tag(self):
        ssot_tag = create_ssot_tag()
        self.assertEqual(ssot_tag, Tag.objects.get(name="SSoT Synced from vSphere"))

    def test_tag_object(self):
        vm, _ = VirtualMachine.objects.get_or_create(
            name="Nautobot VM", cluster=self.test_cluster, status=self.active_status
        )
        tag_object(vm)
        self.assertIn("SSoT Synced from vSphere", [tag.name for tag in vm.tags.all()])
