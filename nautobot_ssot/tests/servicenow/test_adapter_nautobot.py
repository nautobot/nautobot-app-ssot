"""Unit tests for the Nautobot DiffSync adapter."""

from unittest import mock
import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Region, Site
from nautobot.extras.models import Job, JobResult, Status
from nautobot.utilities.testing import TransactionTestCase

from nautobot_ssot_servicenow.jobs import ServiceNowDataTarget
from nautobot_ssot_servicenow.diffsync.adapter_nautobot import NautobotDiffSync


if "job_logs" in settings.DATABASES:
    settings.DATABASES["job_logs"] = settings.DATABASES["job_logs"].copy()
    settings.DATABASES["job_logs"]["TEST"] = {"MIRROR": "default"}


class NautobotDiffSyncTestCase(TransactionTestCase):
    """Test the NautobotDiffSync adapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Per-test-case data setup."""
        status_active = Status.objects.get(slug="active")

        region_1 = Region.objects.create(name="Region 1", slug="region-1")
        region_2 = Region.objects.create(name="Region 2", slug="region-2", parent=region_1)
        region_3 = Region.objects.create(name="Site/Region", slug="site-region", parent=region_1)

        site_1 = Site.objects.create(region=region_2, name="Site 1", slug="site-1", status=status_active)
        site_2 = Site.objects.create(region=region_3, name="Site/Region", slug="site-region", status=status_active)

        manufacturer = Manufacturer.objects.create(name="Cisco", slug="cisco")
        device_type = DeviceType.objects.create(manufacturer=manufacturer, model="CSR 1000v", slug="csr1000v")
        device_role = DeviceRole.objects.create(name="Router", slug="router")

        device_1 = Device.objects.create(
            name="csr1", device_type=device_type, device_role=device_role, site=site_1, status=status_active
        )
        device_2 = Device.objects.create(
            name="csr2", device_type=device_type, device_role=device_role, site=site_2, status=status_active
        )

        Interface.objects.create(device=device_1, name="eth1")
        Interface.objects.create(device=device_1, name="eth2")
        Interface.objects.create(device=device_2, name="eth1")
        Interface.objects.create(device=device_2, name="eth2")

    # Override the JOB_LOGS to None so that the Log Objects are created in the default database.
    # This change is required as JOB_LOGS is a `fake` database pointed at the default. The django
    # database cleanup will fail and cause tests to fail as this is not a real database.
    @mock.patch("nautobot.extras.models.models.JOB_LOGS", None)
    def test_data_loading(self):
        """Test the load() function."""
        job = ServiceNowDataTarget()
        job.job_result = JobResult.objects.create(
            name=job.class_path, obj_type=ContentType.objects.get_for_model(Job), user=None, job_id=uuid.uuid4()
        )
        nds = NautobotDiffSync(job=job, sync=None)
        nds.load()

        self.assertEqual(
            ["Region 1", "Region 2", "Site 1", "Site/Region"],
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
