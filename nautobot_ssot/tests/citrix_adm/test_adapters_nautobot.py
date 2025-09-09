"""Test Nautobot adapter."""

from unittest.mock import MagicMock

from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from django.db.models import ProtectedError
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
)
from nautobot.extras.models import JobResult, Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.citrix_adm.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.citrix_adm.jobs import CitrixAdmDataSource


class NautobotDiffSyncTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        """Initialize shared variables."""
        super().__init__(*args, **kwargs)
        self.hq_site = None
        self.ny_region = None

    def setUp(self):  # pylint: disable=too-many-locals
        """Per-test-case data setup."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")

        self.job = CitrixAdmDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.nb_adapter = NautobotAdapter(job=self.job, sync=None)
        self.job.logger.info = MagicMock()
        self.job.logger.warning = MagicMock()
        self.build_nautobot_objects()

    def build_nautobot_objects(self):
        """Build out Nautobot objects to test loading."""
        test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        region_type = LocationType.objects.get_or_create(name="Region", nestable=True)[0]
        self.ny_region = Location.objects.create(name="NY", location_type=region_type, status=self.status_active)
        self.ny_region.validated_save()

        site_type = LocationType.objects.get_or_create(name="Site", parent=region_type)[0]
        site_type.content_types.add(ContentType.objects.get_for_model(Device))
        self.job.dc_loctype = site_type
        self.job.parent_location = self.ny_region
        self.hq_site = Location.objects.create(
            parent=self.ny_region, name="HQ", location_type=site_type, status=self.status_active
        )
        self.hq_site.validated_save()

        citrix_manu, _ = Manufacturer.objects.get_or_create(name="Citrix")
        srx_devicetype, _ = DeviceType.objects.get_or_create(model="SDX", manufacturer=citrix_manu)
        core_role, _ = Role.objects.get_or_create(name="CORE")
        core_role.content_types.add(ContentType.objects.get_for_model(Device))

        core_router = Device.objects.create(
            name="edge-fw.test.com",
            device_type=srx_devicetype,
            role=core_role,
            serial="FQ123456",
            location=self.hq_site,
            status=self.status_active,
            tenant=test_tenant,
        )
        core_router._custom_field_data["system_of_record"] = "Citrix ADM"  # pylint: disable=protected-access
        core_router.validated_save()
        mgmt_intf = Interface.objects.create(
            name="Management",
            type="virtual",
            device=core_router,
            status=self.status_active,
        )
        mgmt_intf.validated_save()

        global_ns = Namespace.objects.get_or_create(name="Global")[0]
        mgmt4_pf = Prefix.objects.create(
            prefix="10.1.1.0/24", namespace=global_ns, status=self.status_active, tenant=test_tenant
        )
        mgmt6_pf = Prefix.objects.create(
            prefix="2001:db8:3333:4444:5555:6666:7777:8888/128",
            namespace=global_ns,
            status=self.status_active,
            tenant=test_tenant,
        )
        mgmt4_pf._custom_field_data["system_of_record"] = "Citrix ADM"  # pylint: disable=protected-access
        mgmt4_pf.validated_save()
        mgmt6_pf._custom_field_data["system_of_record"] = "Citrix ADM"  # pylint: disable=protected-access
        mgmt6_pf.validated_save()

        mgmt_addr = IPAddress.objects.create(
            address="10.1.1.1/24",
            namespace=global_ns,
            parent=mgmt4_pf,
            status=self.status_active,
            tenant=test_tenant,
        )
        mgmt_addr._custom_field_data["system_of_record"] = "Citrix ADM"  # pylint: disable=protected-access
        mgmt_addr.validated_save()
        mgmt_addr6 = IPAddress.objects.create(
            address="2001:db8:3333:4444:5555:6666:7777:8888/128",
            parent=mgmt6_pf,
            status=self.status_active,
            tenant=test_tenant,
        )
        mgmt_addr6._custom_field_data["system_of_record"] = "Citrix ADM"  # pylint: disable=protected-access
        mgmt_addr6.validated_save()

        IPAddressToInterface.objects.create(ip_address=mgmt_addr, interface=mgmt_intf)
        IPAddressToInterface.objects.create(ip_address=mgmt_addr6, interface=mgmt_intf)
        core_router.primary_ip4 = mgmt_addr
        core_router.primary_ip6 = mgmt_addr6
        core_router.validated_save()

    def test_load_sites(self):
        """Test the load_sites() function."""
        self.nb_adapter.load_sites()
        self.assertEqual(
            {
                "HQ__NY",
            },
            {site.get_unique_id() for site in self.nb_adapter.get_all("datacenter")},
        )
        self.job.logger.info.assert_called_once_with("Loaded Site HQ from Nautobot.")

    def test_load_devices(self):
        """Test the load_devices() function."""
        self.nb_adapter.load_devices()
        self.assertEqual(
            {"edge-fw.test.com"},
            {dev.get_unique_id() for dev in self.nb_adapter.get_all("device")},
        )
        self.job.logger.info.assert_any_call("Loading Device edge-fw.test.com from Nautobot.")

    def test_load_ports_success(self):
        """Test the load_ports() function success."""
        self.nb_adapter.load_devices()
        self.nb_adapter.load_ports()
        self.assertEqual(
            {"Management__edge-fw.test.com"},
            {port.get_unique_id() for port in self.nb_adapter.get_all("port")},
        )

    def test_load_ports_missing_device(self):
        """Test the load_ports() function with missing device."""
        self.nb_adapter.get = MagicMock()
        self.nb_adapter.get.side_effect = ObjectNotFound
        self.nb_adapter.load_ports()
        self.job.logger.warning.assert_called_once_with(
            "Unable to find edge-fw.test.com loaded so skipping loading port Management."
        )

    def test_load_addresses(self):
        """Test the load_addresses() function."""
        self.nb_adapter.load_addresses()
        self.assertEqual(
            {
                "10.1.1.1__Test",
                "2001:db8:3333:4444:5555:6666:7777:8888__Test",
            },
            {addr.get_unique_id() for addr in self.nb_adapter.get_all("address")},
        )

    def test_load_prefixes(self):
        """Test the load_prefix() function."""
        self.nb_adapter.load_prefixes()
        self.assertEqual(
            {"10.1.1.0/24__Global", "2001:db8:3333:4444:5555:6666:7777:8888/128__Global"},
            {pf.get_unique_id() for pf in self.nb_adapter.get_all("prefix")},
        )

    def test_sync_complete(self):
        """Test the sync_complete() method in the NautobotAdapter."""
        self.nb_adapter.objects_to_delete = {
            "devices": [MagicMock()],
            "ports": [MagicMock()],
            "prefixes": [MagicMock()],
            "addresses": [MagicMock()],
        }
        self.nb_adapter.job = MagicMock()
        self.nb_adapter.job.logger.info = MagicMock()

        deleted_objs = []
        for group in ["addresses", "ports", "devices"]:
            deleted_objs.extend(self.nb_adapter.objects_to_delete[group])

        self.nb_adapter.sync_complete(diff=MagicMock(), source=MagicMock())

        for obj in deleted_objs:
            self.assertTrue(obj.delete.called)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["addresses"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["prefixes"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["ports"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["devices"]), 0)
        self.assertTrue(self.nb_adapter.job.logger.info.called)
        self.assertTrue(self.nb_adapter.job.logger.info.call_count, 4)
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[0].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[1].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[2].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[3].startswith("Deleting"))

    def test_sync_complete_protected_error(self):
        """
        Tests that ProtectedError exception is handled when deleting objects from Nautobot.
        """
        mock_dev = MagicMock()
        mock_dev.delete.side_effect = ProtectedError(msg="Cannot delete protected object.", protected_objects=mock_dev)
        self.nb_adapter.objects_to_delete["devices"].append(mock_dev)
        self.nb_adapter.sync_complete(source=self.nb_adapter, diff=MagicMock())
        self.job.logger.info.assert_called()
        self.job.logger.info.calls[1].starts_with("Deletion failed protected object")

    def test_load(self):
        """Test the load() function."""
        self.nb_adapter.load_sites = MagicMock()
        self.nb_adapter.load_devices = MagicMock()
        self.nb_adapter.load_ports = MagicMock()
        self.nb_adapter.load_prefixes = MagicMock()
        self.nb_adapter.load_addresses = MagicMock()
        self.nb_adapter.load()
        self.nb_adapter.load_sites.assert_called_once()
        self.nb_adapter.load_devices.assert_called_once()
        self.nb_adapter.load_ports.assert_called_once()
        self.nb_adapter.load_prefixes.assert_called_once()
        self.nb_adapter.load_addresses.assert_called_once()
