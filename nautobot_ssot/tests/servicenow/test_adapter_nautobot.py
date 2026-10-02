"""Unit tests for the Nautobot DiffSync adapter."""

import datetime

from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer
from nautobot.extras.models import JobResult, Role, Status, Tag

from nautobot_ssot.integrations.servicenow.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.servicenow.jobs import ServiceNowDataTarget


class NautobotDiffSyncTestCase(TestCase):
    """Test the NautobotDiffSync adapter class."""

    job_class = ServiceNowDataTarget
    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Per-test-case data setup."""
        status_active, _ = Status.objects.get_or_create(name="Active")

        reg_loctype = LocationType.objects.update_or_create(name="Region")[0]
        region_1 = Location.objects.create(name="Region 1", location_type=reg_loctype, status=status_active)
        region_2 = Location.objects.create(
            name="Region 2", parent=region_1, location_type=reg_loctype, status=status_active
        )
        region_3 = Location.objects.create(
            name="Region 3", parent=region_1, location_type=reg_loctype, status=status_active
        )

        site_loctype = LocationType.objects.update_or_create(name="Site")[0]
        site_1 = Location.objects.create(
            parent=region_2, name="Site 1", location_type=site_loctype, status=status_active
        )
        site_2 = Location.objects.create(
            parent=region_3, name="Site 2", location_type=site_loctype, status=status_active
        )

        manufacturer, _ = Manufacturer.objects.get_or_create(name="Cisco")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CSR 1000v")
        device_role = Role.objects.create(name="Router")

        device_1 = Device.objects.create(
            name="csr1", device_type=device_type, role=device_role, location=site_1, status=status_active
        )
        device_2 = Device.objects.create(
            name="csr2", device_type=device_type, role=device_role, location=site_2, status=status_active
        )

        Interface.objects.create(device=device_1, name="eth1", status=status_active)
        Interface.objects.create(device=device_1, name="eth2", status=status_active)
        Interface.objects.create(device=device_2, name="eth1", status=status_active)
        Interface.objects.create(device=device_2, name="eth2", status=status_active)

    def test_data_loading(self):
        """Test the load() function."""
        job = self.job_class()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        # Get rid of the automatically created 'site' type locations from the ACI integration.
        # TODO: I am not in love with this approach, there should rather be a way to disable automatic creation of
        #  objects from the different integrations.
        Location.objects.filter(location_type__name="Site").exclude(name__contains="Site").delete()
        nds = NautobotDiffSync(job=job, sync=None)
        nds.load()

        self.assertEqual(
            ["Region 1", "Region 2", "Region 3", "Site 1", "Site 2"],
            sorted(loc.get_unique_id() for loc in nds.get_all("location")),
        )
        self.assertEqual(
            ["csr1", "csr2"],
            sorted(dev.get_unique_id() for dev in nds.get_all("device")),
        )
        self.assertEqual(
            ["csr1__eth1", "csr1__eth2", "csr2__eth1", "csr2__eth2"],
            sorted(intf.get_unique_id() for intf in nds.get_all("interface")),
        )

    def test_tag_involved_objects(self):
        """Test that tag_involved_objects() bulk-applies the tag and custom field to synced objects."""
        job = self.job_class()
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        Location.objects.filter(location_type__name="Site").exclude(name__contains="Site").delete()

        source = NautobotDiffSync(job=job, sync=None)
        source.load()
        # A second adapter loaded from the same database stands in for a target where every object
        # was successfully synced, so the target.get() existence check succeeds for all of them.
        target = NautobotDiffSync(job=job, sync=None)
        target.load()

        source.tag_involved_objects(target=target)

        tag = Tag.objects.get(name="SSoT Synced to ServiceNow")
        today = datetime.date.today().isoformat()

        # Taggable models receive both the tag and the "last synced" custom field stamp.
        for device in Device.objects.all():
            self.assertIn(tag, device.tags.all())
            self.assertEqual(device.cf["ssot_synced_to_servicenow"], today)

        # Manufacturer is not taggable, but should still receive the custom field stamp.
        manufacturer = Manufacturer.objects.get(name="Cisco")
        self.assertEqual(manufacturer.cf["ssot_synced_to_servicenow"], today)

        # Re-running must be idempotent and not create duplicate tag assignments.
        source.tag_involved_objects(target=target)
        self.assertEqual(Device.objects.get(name="csr1").tags.count(), 1)
