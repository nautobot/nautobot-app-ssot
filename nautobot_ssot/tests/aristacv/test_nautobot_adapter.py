"""Unit tests for the Nautoobt DiffSync adapter class."""
import uuid
from unittest.mock import MagicMock, patch
from django.contrib.contenttypes.models import ContentType

from nautobot.dcim.models import Device, DeviceRole, DeviceType, Manufacturer, Site
from nautobot.extras.models import Job, JobResult, Status
from nautobot.utilities.testing import TransactionTestCase
from nautobot_ssot_aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot_aristacv.jobs import CloudVisionDataSource


class NautobotAdapterTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    def setUp(self):
        """Create Nautobot objects to test with."""
        status_active, _ = Status.objects.get_or_create(name="Active", slug="active")
        arista_manu, _ = Manufacturer.objects.get_or_create(name="Arista", slug="arista")

        hq_site, _ = Site.objects.get_or_create(name="HQ")

        csr_devicetype, _ = DeviceType.objects.get_or_create(
            model="CSR1000v", slug="csr1000v", manufacturer=arista_manu
        )
        rtr_devicerole, _ = DeviceRole.objects.get_or_create(name="Router", slug="rtr")

        Device.objects.get_or_create(
            name="ams01-rtr-01",
            device_type=csr_devicetype,
            status=status_active,
            device_role=rtr_devicerole,
            site=hq_site,
        )
        Device.objects.get_or_create(
            name="ams01-rtr-02",
            device_type=csr_devicetype,
            status=status_active,
            device_role=rtr_devicerole,
            site=hq_site,
        )

        self.job = CloudVisionDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, obj_type=ContentType.objects.get_for_model(Job), user=None, job_id=uuid.uuid4()
        )
        self.nb_adapter = NautobotAdapter(job=self.job)

    def test_load_devices(self):
        """Test the load_devices() function."""
        mock_nautobot = MagicMock()
        mock_nautobot.get_device_version = MagicMock()
        mock_nautobot.get_device_version.return_value = "1.0"

        with patch("nautobot_ssot_aristacv.utils.nautobot.get_device_version", mock_nautobot.get_device_version):
            self.nb_adapter.load_devices()
        self.assertEqual(
            {dev.name for dev in Device.objects.filter(device_type__manufacturer__slug="arista")},
            {dev.get_unique_id() for dev in self.nb_adapter.get_all("device")},
        )
