"""Unit tests for the ACI Nautobot DiffSync adapter."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter, Diff
from diffsync.enum import DiffSyncModelFlags
from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import Role, Status, Tag

from nautobot_ssot.integrations.aci.constant import PLUGIN_CFG
from nautobot_ssot.integrations.aci.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aci.diffsync.models.base import DeviceType as BaseDeviceType

ACI_TAG = "ACI"


class EmptySourceAdapter(Adapter):
    """Source adapter representing a fabric that has none of the existing Device Types."""

    device_type = BaseDeviceType
    top_level = ["device_type"]


@patch.dict(PLUGIN_CFG, {"tag": ACI_TAG})
class TestNautobotAdapterDeviceTypes(TestCase):
    """Test handling of Device Types shared by multiple ACI fabrics (issue #685)."""

    def setUp(self):
        """Create Device Types used by two different fabrics plus an unused one."""
        super().setUp()
        self.aci_tag, _ = Tag.objects.get_or_create(name=ACI_TAG)
        self.fabric_a_tag, _ = Tag.objects.get_or_create(name="FabricA")
        self.fabric_b_tag, _ = Tag.objects.get_or_create(name="FabricB")
        for tag in (self.aci_tag, self.fabric_a_tag, self.fabric_b_tag):
            tag.content_types.add(ContentType.objects.get_for_model(Device))
            tag.content_types.add(ContentType.objects.get_for_model(DeviceType))

        status = Status.objects.get_or_create(name="Active")[0]
        status.content_types.add(ContentType.objects.get_for_model(Device))
        site_type = LocationType.objects.get_or_create(name="Site")[0]
        site_type.content_types.add(ContentType.objects.get_for_model(Device))
        location = Location.objects.create(name="Site A", location_type=site_type, status=status)
        role = Role.objects.create(name="leaf")
        role.content_types.add(ContentType.objects.get_for_model(Device))
        manufacturer = Manufacturer.objects.get_or_create(name="Cisco")[0]

        self.dt_fabric_a = DeviceType.objects.create(model="N9K-FABRIC-A", manufacturer=manufacturer)
        self.dt_fabric_b = DeviceType.objects.create(model="N9K-FABRIC-B", manufacturer=manufacturer)
        self.dt_unused = DeviceType.objects.create(model="N9K-UNUSED", manufacturer=manufacturer)
        for device_type in (self.dt_fabric_a, self.dt_fabric_b, self.dt_unused):
            device_type.tags.add(self.aci_tag)

        device_a = Device.objects.create(
            name="leaf-a", device_type=self.dt_fabric_a, role=role, location=location, status=status
        )
        device_a.tags.add(self.aci_tag, self.fabric_a_tag)
        device_b = Device.objects.create(
            name="leaf-b", device_type=self.dt_fabric_b, role=role, location=location, status=status
        )
        device_b.tags.add(self.aci_tag, self.fabric_b_tag)

        self.job = MagicMock()
        self.adapter = NautobotAdapter(job=self.job, sync=None, site_name="FabricB")

    def test_load_devicetypes_skips_unmatched_types_used_by_other_fabrics(self):
        """Device Types used by another fabric's Devices are flagged SKIP_UNMATCHED_DST."""
        self.adapter.load_devicetypes()
        flagged = self.adapter.get("device_type", {"model": "N9K-FABRIC-A", "part_nbr": ""})
        own = self.adapter.get("device_type", {"model": "N9K-FABRIC-B", "part_nbr": ""})
        unused = self.adapter.get("device_type", {"model": "N9K-UNUSED", "part_nbr": ""})
        self.assertTrue(flagged.model_flags & DiffSyncModelFlags.SKIP_UNMATCHED_DST)
        self.assertFalse(own.model_flags & DiffSyncModelFlags.SKIP_UNMATCHED_DST)
        self.assertFalse(unused.model_flags & DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    def test_sync_does_not_delete_device_types_in_use(self):
        """Syncing fabric B only deletes Device Types that no Device references."""
        self.adapter.load_devicetypes()
        source = EmptySourceAdapter()
        self.adapter.sync_from(source)

        self.assertTrue(DeviceType.objects.filter(pk=self.dt_fabric_a.pk).exists())
        self.assertTrue(DeviceType.objects.filter(pk=self.dt_fabric_b.pk).exists())
        self.assertFalse(DeviceType.objects.filter(pk=self.dt_unused.pk).exists())
        self.assertEqual(self.adapter.objects_to_delete["devicetype"], [])

    def test_delete_defers_until_sync_complete(self):
        """NautobotDeviceType.delete() defers removal and sync_complete skips Device Types still in use."""
        self.adapter.load_devicetypes()
        own = self.adapter.get("device_type", {"model": "N9K-FABRIC-B", "part_nbr": ""})
        unused = self.adapter.get("device_type", {"model": "N9K-UNUSED", "part_nbr": ""})
        own.delete()
        unused.delete()
        # Nothing is removed from the database until sync_complete runs.
        self.assertTrue(DeviceType.objects.filter(pk=self.dt_unused.pk).exists())

        self.adapter.sync_complete(EmptySourceAdapter(), Diff())

        self.assertTrue(DeviceType.objects.filter(pk=self.dt_fabric_b.pk).exists())
        self.assertFalse(DeviceType.objects.filter(pk=self.dt_unused.pk).exists())
        self.job.logger.warning.assert_any_call(
            "Device Type N9K-FABRIC-B is still in use by Devices and will not be deleted."
        )
