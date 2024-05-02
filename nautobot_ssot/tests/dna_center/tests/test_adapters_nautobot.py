"""Unit tests for the Nautobot DiffSync adapter."""

import uuid
from unittest.mock import MagicMock, patch
from diffsync.exceptions import ObjectNotFound
from django.contrib.contenttypes.models import ContentType
from nautobot.dcim.models import (
    Manufacturer,
    Location,
    LocationType,
    Device,
    DeviceType,
    Platform,
    Interface,
)
from nautobot.extras.models import Status, JobResult, Role
from nautobot.ipam.models import IPAddress, Namespace, Prefix, IPAddressToInterface
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot_dna_center.jobs import DnaCenterDataSource
from nautobot_ssot_dna_center.diffsync.adapters.nautobot import NautobotAdapter


class NautobotDiffSyncTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        """Initialize shared variables."""
        super().__init__(*args, **kwargs)
        self.ny_region = None
        self.hq_site = None
        self.loc_type = None
        self.floor_loc = None

    def setUp(self):  # pylint: disable=too-many-locals
        """Per-test-case data setup."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")

        job = DnaCenterDataSource()
        job.job_result = JobResult.objects.create(
            name=job.class_path, task_name="fake task", user=None, id=uuid.uuid4()
        )
        self.nb_adapter = NautobotAdapter(job=job, sync=None)
        self.nb_adapter.job = MagicMock()
        self.nb_adapter.job.logger.info = MagicMock()
        self.nb_adapter.job.logger.warning = MagicMock()

    def build_nautobot_objects(self):  # pylint: disable=too-many-locals, too-many-statements
        """Build out Nautobot objects to test loading."""
        self.loc_type = LocationType.objects.get(name="Region")
        global_region = Location.objects.create(name="Global", status=self.status_active, location_type=self.loc_type)
        global_region.custom_field_data["system_of_record"] = "DNA Center"
        global_region.validated_save()
        self.ny_region = Location.objects.create(
            name="NY", location_type=self.loc_type, parent=global_region, status=self.status_active
        )
        self.ny_region.custom_field_data["system_of_record"] = "DNA Center"
        self.ny_region.validated_save()
        self.loc_type = LocationType.objects.get(name="Site")
        self.hq_site = Location.objects.create(
            parent=self.ny_region, name="HQ", status=self.status_active, location_type=self.loc_type
        )
        self.hq_site.custom_field_data["system_of_record"] = "DNA Center"
        self.hq_site.validated_save()

        self.loc_type = LocationType.objects.get(name="Floor")
        self.floor_loc = Location.objects.create(
            name="HQ Floor 1",
            parent=self.hq_site,
            location_type=self.loc_type,
            status=self.status_active,
        )
        self.floor_loc.custom_field_data["system_of_record"] = "DNA Center"
        self.floor_loc.validated_save()

        cisco_manu = Manufacturer.objects.create(name="Cisco")
        csr_devicetype = DeviceType.objects.create(model="Cisco Catalyst 9300 Switch", manufacturer=cisco_manu)
        leaf_role = Role.objects.create(name="LEAF")
        leaf_role.content_types.add(ContentType.objects.get_for_model(Device))
        spine_role = Role.objects.create(name="SPINE")
        spine_role.content_types.add(ContentType.objects.get_for_model(Device))
        ios_platform = Platform.objects.create(name="IOS", napalm_driver="ios")
        leaf1_dev = Device.objects.create(
            name="leaf1.abc.inc",
            location=self.floor_loc,
            status=self.status_active,
            device_type=csr_devicetype,
            role=leaf_role,
            platform=ios_platform,
            serial="FCW2214L0VK",
        )
        leaf1_dev.custom_field_data["system_of_record"] = "DNA Center"
        leaf2_dev = Device.objects.create(
            name="leaf2.abc.inc",
            location=self.floor_loc,
            status=self.status_active,
            device_type=csr_devicetype,
            role=leaf_role,
            platform=ios_platform,
            serial="FCW2214L0UZ",
        )
        leaf2_dev.custom_field_data["system_of_record"] = "DNA Center"
        spine1_dev = Device.objects.create(
            name="spine1.abc.in",
            location=self.floor_loc,
            status=self.status_active,
            device_type=csr_devicetype,
            role=spine_role,
            platform=ios_platform,
            serial="FCW2212D05S",
        )
        spine1_dev.custom_field_data["system_of_record"] = "DNA Center"
        spine1_dev.validated_save()

        unknown_role = Role.objects.create(name="UNKNOWN")
        unknown_role.content_types.add(ContentType.objects.get_for_model(Device))
        meraki_ap = Device.objects.create(
            name="",
            location=self.floor_loc,
            status=self.status_active,
            device_type=DeviceType.objects.create(model="MR42", manufacturer=cisco_manu),
            role=unknown_role,
            platform=Platform.objects.create(name="meraki", napalm_driver="meraki"),
            serial="R3JE-OYG4-RCDE",
        )
        meraki_ap.custom_field_data["system_of_record"] = "DNA Center"
        meraki_ap.validated_save()

        leaf1_mgmt = Interface.objects.create(
            device=leaf1_dev,
            name="Management",
            status=self.status_active,
            mtu=1500,
            type="virtual",
            mac_address="aa:bb:cc:dd:ee:f1",
        )
        leaf1_mgmt.custom_field_data["system_of_record"] = "DNA Center"
        leaf1_mgmt.validated_save()
        leaf2_mgmt = Interface.objects.create(
            device=leaf2_dev,
            name="Management",
            status=self.status_active,
            mtu=1500,
            type="virtual",
            mac_address="aa:bb:cc:dd:ee:f2",
        )
        leaf2_mgmt.custom_field_data["system_of_record"] = "DNA Center"
        leaf2_mgmt.validated_save()
        spine1_mgmt = Interface.objects.create(
            device=spine1_dev,
            name="Management",
            status=self.status_active,
            mtu=1500,
            type="virtual",
            mac_address="aa:bb:cc:dd:ee:f3",
        )
        spine1_mgmt.custom_field_data["system_of_record"] = "DNA Center"
        spine1_mgmt.validated_save()

        ap_mgmt = Interface.objects.create(
            device=meraki_ap,
            name="Management",
            status=self.status_active,
            mtu=1500,
            type="virtual",
            mac_address="aa:bb:cc:dd:ee:f4",
        )
        ap_mgmt.custom_field_data["system_of_record"] = "DNA Center"
        ap_mgmt.validated_save()

        test_ns = Namespace.objects.create(name="Global")

        leaf1_pf = Prefix.objects.create(
            prefix="10.10.10.0/24",
            namespace=test_ns,
            status=self.status_active,
        )
        leaf1_ip = IPAddress.objects.create(
            address="10.10.10.1/24",
            parent=leaf1_pf,
            status=self.status_active,
        )
        leaf1_ip.custom_field_data["system_of_record"] = "DNA Center"
        leaf1_ip.validated_save()

        IPAddressToInterface.objects.create(ip_address=leaf1_ip, interface=leaf1_mgmt)

        leaf1_mgmt.device.primary_ip4 = leaf1_ip
        leaf1_mgmt.device.validated_save()

        leaf2_pf = Prefix.objects.create(
            prefix="10.10.11.0/24",
            namespace=test_ns,
            status=self.status_active,
        )
        leaf2_ip = IPAddress.objects.create(
            address="10.10.11.1/24",
            parent=leaf2_pf,
            status=self.status_active,
        )
        leaf2_ip.custom_field_data["system_of_record"] = "DNA Center"
        leaf2_ip.validated_save()

        IPAddressToInterface.objects.create(ip_address=leaf2_ip, interface=leaf2_mgmt)

        leaf2_mgmt.device.primary_ip4 = leaf2_ip
        leaf2_mgmt.device.validated_save()

        spine1_pf = Prefix.objects.create(
            prefix="10.10.12.0/24",
            namespace=test_ns,
            status=self.status_active,
        )
        spine1_ip = IPAddress.objects.create(
            address="10.10.12.1/24",
            parent=spine1_pf,
            status=self.status_active,
        )
        spine1_ip.custom_field_data["system_of_record"] = "DNA Center"
        spine1_ip.validated_save()

        IPAddressToInterface.objects.create(ip_address=spine1_ip, interface=spine1_mgmt)

        spine1_mgmt.device.primary_ip4 = spine1_ip
        spine1_mgmt.device.validated_save()

        ap_pf = Prefix.objects.create(
            prefix="10.10.13.0/24",
            namespace=test_ns,
            status=self.status_active,
        )

        ap_ip = IPAddress.objects.create(
            address="10.10.13.1/24",
            parent=ap_pf,
            status=self.status_active,
        )
        ap_ip.custom_field_data["system_of_record"] = "DNA Center"
        ap_ip.validated_save()

        IPAddressToInterface.objects.create(ip_address=ap_ip, interface=ap_mgmt)

        ap_mgmt.device.primary_ip4 = ap_ip
        ap_mgmt.device.validated_save()

    def test_data_loading(self):
        """Test the load() function."""
        self.build_nautobot_objects()
        self.nb_adapter.load()
        self.assertEqual(
            ["Global__None", "NY__Global"],
            sorted(loc.get_unique_id() for loc in self.nb_adapter.get_all("area")),
        )
        self.assertEqual(
            ["HQ"],
            sorted(site.get_unique_id() for site in self.nb_adapter.get_all("building")),
        )
        self.assertEqual(
            ["HQ Floor 1__HQ"],
            sorted(loc.get_unique_id() for loc in self.nb_adapter.get_all("floor")),
        )
        self.assertEqual(
            ["", "leaf1.abc.inc", "leaf2.abc.inc", "spine1.abc.in"],
            sorted(dev.get_unique_id() for dev in self.nb_adapter.get_all("device")),
        )
        self.assertEqual(
            [
                "Management__",
                "Management__leaf1.abc.inc",
                "Management__leaf2.abc.inc",
                "Management__spine1.abc.in",
            ],
            sorted(port.get_unique_id() for port in self.nb_adapter.get_all("port")),
        )
        self.assertEqual(
            [
                "10.10.10.1__Global",
                "10.10.11.1__Global",
                "10.10.12.1__Global",
                "10.10.13.1__Global",
            ],
            sorted(ipaddr.get_unique_id() for ipaddr in self.nb_adapter.get_all("ipaddress")),
        )

    def test_load_regions_failure(self):
        """Test the load_regions method failing with loading duplicate Regions."""
        self.build_nautobot_objects()
        self.nb_adapter.load()
        self.nb_adapter.load_regions()
        self.nb_adapter.job.logger.warning.assert_called_with("Region NY already loaded so skipping duplicate.")

    @patch("nautobot_ssot_dna_center.diffsync.adapters.nautobot.OrmLocationType")
    @patch("nautobot_ssot_dna_center.diffsync.adapters.nautobot.OrmLocation")
    def test_load_floors_missing_building(self, mock_floors, mock_loc_type):
        """Test the load_floors method failing with missing Building."""
        mock_floor = MagicMock()
        mock_floor.name = "HQ - Floor 1"
        mock_floor.parent = MagicMock()
        mock_floor.parent.name = "Missing"
        mock_floor.tenant = None
        mock_floor.id = uuid.uuid4()
        mock_loc_type.objects.get.return_value = mock_loc_type
        mock_floors.objects.filter.return_value = [mock_floor]
        self.nb_adapter.get = MagicMock()
        self.nb_adapter.get.side_effect = [ObjectNotFound()]
        self.nb_adapter.load_floors()
        self.nb_adapter.job.logger.warning.assert_called_with(
            "Unable to load building Missing for floor HQ - Floor 1. "
        )

    def test_sync_complete(self):
        """Test the sync_complete() method in the NautobotAdapter."""
        self.nb_adapter.objects_to_delete = {
            "ipaddresses": [MagicMock()],
            "prefixes": [MagicMock()],
            "ports": [MagicMock()],
            "devices": [MagicMock()],
            "floors": [MagicMock(), MagicMock()],
            "sites": [MagicMock()],
            "regions": [],
        }
        self.nb_adapter.job = MagicMock()
        self.nb_adapter.job.logger.info = MagicMock()

        deleted_objs = []
        for group in ["ipaddresses", "prefixes", "ports", "devices", "floors", "sites"]:
            deleted_objs.extend(self.nb_adapter.objects_to_delete[group])

        self.nb_adapter.sync_complete(diff=MagicMock(), source=MagicMock())

        for obj in deleted_objs:
            self.assertTrue(obj.delete.called)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["ipaddresses"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["prefixes"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["devices"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["ports"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["floors"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["sites"]), 0)
        self.assertEqual(len(self.nb_adapter.objects_to_delete["regions"]), 0)
        self.assertTrue(self.nb_adapter.job.logger.info.called)
        self.assertTrue(self.nb_adapter.job.logger.info.call_count, 5)
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[0].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[1].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[2].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[3].startswith("Deleting"))
        self.assertTrue(self.nb_adapter.job.logger.info.call_args_list[4].startswith("Deleting"))
