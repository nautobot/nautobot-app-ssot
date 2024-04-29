"""Unit tests for the Nautoobt DiffSync adapter class."""

from unittest.mock import MagicMock, patch

from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import JobResult, Role, Status
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.jobs import CloudVisionDataSource


class NautobotAdapterTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    job_class = CloudVisionDataSource
    databases = (
        "default",
        "job_logs",
    )

    def setUp(self):
        """Create Nautobot objects to test with."""
        status_active, _ = Status.objects.get_or_create(name="Active")
        arista_manu, _ = Manufacturer.objects.get_or_create(name="Arista")

        loc_type = LocationType.objects.get_or_create(name="Site")[0]
        hq_site, _ = Location.objects.get_or_create(name="HQ", status=status_active, location_type=loc_type)

        csr_devicetype, _ = DeviceType.objects.get_or_create(model="CSR1000v", manufacturer=arista_manu)
        rtr_devicerole, _ = Role.objects.get_or_create(name="Router")

        Device.objects.get_or_create(
            name="ams01-rtr-01",
            device_type=csr_devicetype,
            status=status_active,
            role=rtr_devicerole,
            location=hq_site,
        )
        Device.objects.get_or_create(
            name="ams01-rtr-02",
            device_type=csr_devicetype,
            status=status_active,
            role=rtr_devicerole,
            location=hq_site,
        )

        self.job = self.job_class()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.nb_adapter = NautobotAdapter(job=self.job)

    def test_load_devices(self):
        """Test the load_devices() function."""
        mock_nautobot = MagicMock()
        mock_nautobot.get_device_version = MagicMock()
        mock_nautobot.get_device_version.return_value = "1.0"

        with patch(
            "nautobot_ssot.integrations.aristacv.utils.nautobot.get_device_version", mock_nautobot.get_device_version
        ):
            self.nb_adapter.load_devices()
        self.assertEqual(
            {dev.name for dev in Device.objects.filter(device_type__manufacturer__name="Arista")},
            {dev.get_unique_id() for dev in self.nb_adapter.get_all("device")},
        )
