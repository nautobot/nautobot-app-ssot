"""Test DNA Center adapter."""

import uuid
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import (
    Controller,
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
)
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, JobResult, Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

from nautobot_ssot.integrations.dna_center.diffsync.adapters.dna_center import DnaCenterAdapter
from nautobot_ssot.integrations.dna_center.jobs import DnaCenterDataSource
from nautobot_ssot.tests.dna_center.fixtures import (
    DEVICE_DETAIL_FIXTURE,
    DEVICE_FIXTURE,
    EXPECTED_BUILDING_MAP,
    EXPECTED_DNAC_LOCATION_MAP,
    EXPECTED_DNAC_LOCATION_MAP_W_JOB_LOCATION_MAP,
    EXPECTED_DNAC_LOCATION_MAP_W_MULTI_LEVEL_LOCATIONS,
    EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL,
    EXPECTED_FLOORS,
    LOCATION_FIXTURE,
    MULTI_LEVEL_LOCATION_FIXTURE,
    PORT_FIXTURE,
)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_import_global": True}})
class TestDnaCenterAdapterTestCase(TransactionTestCase):  # pylint: disable=too-many-public-methods, too-many-instance-attributes
    """Test NautobotSsotDnaCenterAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=too-many-statements
        """Initialize test case."""
        super().setUp()
        self.dna_center_client = MagicMock()
        self.dna_center_client.get_devices.return_value = DEVICE_FIXTURE
        self.dna_center_client.find_address_and_type.side_effect = [
            ("", "floor"),
            ("", "building"),
            ("", "area"),
        ]
        self.dna_center_client.find_latitude_and_longitude.return_value = ("", "")
        self.dna_center_client.get_device_detail.return_value = DEVICE_DETAIL_FIXTURE
        self.dna_center_client.get_model_name.return_value = "WS-C3850-24P-L"
        self.dna_center_client.parse_site_hierarchy.return_value = {
            "areas": ["Global", "NY"],
            "building": "Building1",
            "floor": "Floor1",
        }
        self.dna_center_client.get_port_info.return_value = PORT_FIXTURE
        self.dna_center_client.get_port_type.return_value = "virtual"
        self.dna_center_client.get_port_status.return_value = "active"

        sor_cf_dict = {
            "type": CustomFieldTypeChoices.TYPE_TEXT,
            "key": "system_of_record",
            "label": "System of Record",
        }
        self.sor_cf, _ = CustomField.objects.update_or_create(key=sor_cf_dict["key"], defaults=sor_cf_dict)
        self.status_active = Status.objects.get(name="Active")
        self.reg_loc_type = LocationType.objects.get_or_create(name="Region", nestable=True)[0]
        self.hq_area = Location.objects.create(name="NY", location_type=self.reg_loc_type, status=self.status_active)
        self.site_loc_type = LocationType.objects.get_or_create(name="Site", parent=self.reg_loc_type)[0]
        self.site_loc_type.content_types.add(ContentType.objects.get_for_model(Device))
        self.hq_site = Location.objects.create(
            name="HQ", parent=self.hq_area, location_type=self.site_loc_type, status=self.status_active
        )
        self.hq_site.validated_save()

        self.floor_loc_type = LocationType.objects.get_or_create(name="Floor", parent=self.site_loc_type)[0]
        self.floor_loc_type.content_types.add(ContentType.objects.get_for_model(Device))

        cisco_manu = Manufacturer.objects.get_or_create(name="Cisco")[0]
        catalyst_devicetype = DeviceType.objects.get_or_create(model="WS-C3850-24P-L", manufacturer=cisco_manu)[0]
        core_role, created = Role.objects.get_or_create(name="CORE")
        if created:
            core_role.content_types.add(ContentType.objects.get_for_model(Device))

        self.test_dev = Device.objects.create(
            name="spine1.abc.in",
            device_type=catalyst_devicetype,
            role=core_role,
            serial="FCW2212D05S",
            location=self.hq_site,
            status=self.status_active,
        )
        self.test_dev.validated_save()
        self.intf = Interface.objects.create(
            name="Vlan823", type="virtual", device=self.test_dev, status=self.status_active
        )
        self.intf.validated_save()

        self.namespace = Namespace.objects.get_or_create(name="Global")[0]

        self.prefix = Prefix.objects.create(
            prefix="10.10.20.0/24",
            status=self.status_active,
            namespace=self.namespace,
        )
        self.addr = IPAddress.objects.create(
            address="10.10.20.80/24",
            parent=self.prefix,
            status=self.status_active,
        )
        self.ip_to_intf = IPAddressToInterface.objects.create(
            ip_address=self.addr,
            interface=self.intf,
        )

        dnac = Controller.objects.get_or_create(name="DNA Center", status=self.status_active, location=self.hq_site)[0]
        self.job = DnaCenterDataSource()
        self.job.area_loctype = self.reg_loc_type
        self.job.building_loctype = self.site_loc_type
        self.job.floor_loctype = self.floor_loc_type
        self.job.dnac = dnac
        self.job.location_map = {}
        self.job.hostname_map = {}
        self.job.logger.warning = MagicMock()
        self.job.logger.error = MagicMock()
        self.job.logger.info = MagicMock()
        self.job.controller_group = ControllerManagedDeviceGroup.objects.get_or_create(
            name="DNA Center Managed Devices", controller=dnac
        )[0]
        self.job.debug = True
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", user=None, id=uuid.uuid4()
        )
        self.dna_center = DnaCenterAdapter(job=self.job, sync=None, client=self.dna_center_client, tenant=None)
        self.dna_center.dnac_location_map = EXPECTED_DNAC_LOCATION_MAP
        self.dna_center.building_map = EXPECTED_BUILDING_MAP

    def test_build_dnac_location_map(self):
        """Test Nautobot adapter build_dnac_location_map method."""
        self.dna_center.dnac_location_map = {}
        actual_floors = self.dna_center.build_dnac_location_map(locations=LOCATION_FIXTURE)
        expected = EXPECTED_DNAC_LOCATION_MAP
        self.assertEqual(self.dna_center.dnac_location_map, expected)
        self.assertEqual(actual_floors, EXPECTED_FLOORS)

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_import_global": False}})
    def test_build_dnac_location_map_wo_global(self):
        """Test Nautobot adapter build_dnac_location_map method without global."""
        self.dna_center.dnac_location_map = {}
        self.dna_center.build_dnac_location_map(locations=LOCATION_FIXTURE)
        expected = EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL
        self.assertEqual(self.dna_center.dnac_location_map, expected)

    def test_build_dnac_location_map_w_job_location_map(self):
        """Test Nautobot adapter build_dnac_location_map method when used with the Job location map."""
        self.dna_center.dnac_location_map = {}
        self.job.location_map = {
            "SanJose": {"name": "San Jose", "parent": "Califonia", "area_parent": "USA"},
            "Antartica2": {"name": "South Pole"},
        }
        self.dna_center.build_dnac_location_map(locations=LOCATION_FIXTURE)
        self.assertEqual(
            sorted(self.dna_center.dnac_location_map), sorted(EXPECTED_DNAC_LOCATION_MAP_W_JOB_LOCATION_MAP)
        )

    def test_load_locations_success(self):
        """Test Nautobot SSoT for Cisco DNA Center load_locations() function successfully."""
        self.dna_center.build_dnac_location_map = MagicMock()
        self.dna_center_client.get_location.return_value = [{"name": "NY"}]
        self.dna_center.load_locations()
        self.dna_center_client.get_locations.assert_called()
        self.dna_center.build_dnac_location_map.assert_called_once()

    def test_load_locations_failure(self):
        """Test Nautobot SSoT for Cisco DNA Center load_locations() function fails."""
        self.dna_center_client.get_locations.return_value = []
        self.dna_center.load_locations()
        self.dna_center.job.logger.error.assert_called_once_with(
            "No location data was returned from DNA Center. Unable to proceed."
        )

    def test_load_device_location_tree_w_floor(self):
        """Test Nautobot SSoT for Cisco DNA Center load_device_location_tree() function with Device that has floor Location."""
        self.dna_center.dnac_location_map = {
            "1": {
                "name": "Global",
                "parent": None,
                "parent_of_parent": None,
            },
            "2": {
                "name": "USA",
                "parent": "Global",
                "parent_of_parent": None,
            },
            "3": {
                "name": "New York",
                "parent": "USA",
                "parent_of_parent": "Global",
            },
            "4": {
                "name": "NYC",
                "parent": "New York",
                "parent_of_parent": "USA",
            },
            "5": {"name": "HQ", "parent": "NYC", "parent_of_parent": "New York"},
            "6": {"name": "1st Floor", "parent": "HQ"},
        }
        self.dna_center.building_map = {
            "5": {
                "name": "HQ",
                "id": "5",
                "parentId": "4",
                "additionalInfo": [
                    {
                        "nameSpace": "Location",
                        "attributes": {
                            "country": "United States",
                            "address": "123 Broadway, New York City, New York 12345, United States",
                            "latitude": "40.758746",
                            "addressInheritedFrom": "2",
                            "type": "building",
                            "longitude": "-73.978660",
                        },
                    }
                ],
                "siteHierarchy": "/1/2/3/4/5/",
            },
        }
        mock_loc_data = {"areas": ["Global", "USA", "New York", "NYC"], "building": "HQ", "floor": "1st Floor"}
        mock_dev_details = {"siteHierarchyGraphId": "/1/2/3/4/5/6/"}
        self.dna_center.load_device_location_tree(dev_details=mock_dev_details, loc_data=mock_loc_data)
        self.assertEqual(
            {"HQ - 1st Floor__HQ__NYC"},
            {dev.get_unique_id() for dev in self.dna_center.get_all("floor")},
        )
        self.assertEqual(
            {"HQ__NYC"},
            {dev.get_unique_id() for dev in self.dna_center.get_all("building")},
        )
        loaded_bldgs = self.dna_center.get_all("building")
        self.assertEqual(loaded_bldgs[0].area_parent, "New York")
        self.assertEqual(
            {"Global__None__None", "USA__Global__None", "New York__USA__Global", "NYC__New York__USA"},
            {dev.get_unique_id() for dev in self.dna_center.get_all("area")},
        )

    def test_load_device_location_tree_wo_floor(self):
        """Test Nautobot SSoT for Cisco DNA Center load_device_location_tree() function with Device that doesn't have a floor Location."""
        self.dna_center.dnac_location_map = {
            "1": {
                "name": "Global",
                "parent": None,
                "parent_of_parent": None,
            },
            "2": {
                "name": "USA",
                "parent": "Global",
                "parent_of_parent": None,
            },
            "3": {
                "name": "New York",
                "parent": "USA",
                "parent_of_parent": "Global",
            },
            "4": {
                "name": "NYC",
                "parent": "New York",
                "parent_of_parent": "USA",
            },
            "5": {"name": "HQ", "parent": "NYC", "parent_of_parent": "New York"},
        }
        self.dna_center.building_map = {
            "5": {
                "name": "HQ",
                "id": "5",
                "parentId": "4",
                "additionalInfo": [
                    {
                        "nameSpace": "Location",
                        "attributes": {
                            "country": "United States",
                            "address": "123 Broadway, New York City, New York 12345, United States",
                            "latitude": "40.758746",
                            "addressInheritedFrom": "2",
                            "type": "building",
                            "longitude": "-73.978660",
                        },
                    }
                ],
                "siteHierarchy": "/1/2/3/4/5/",
            },
        }
        mock_loc_data = {"areas": ["Global", "USA", "New York", "NYC"], "building": "HQ"}
        mock_dev_details = {"siteHierarchyGraphId": "/1/2/3/4/5/"}
        self.dna_center.load_device_location_tree(dev_details=mock_dev_details, loc_data=mock_loc_data)
        self.assertEqual(len(self.dna_center.get_all("floor")), 0)

    def test_load_devices(self):
        """Test Nautobot SSoT for Cisco DNA Center load_devices() function."""
        self.dna_center.load_ports = MagicMock()
        self.dna_center.load_devices()
        self.assertEqual(
            {f"{dev['hostname']}" for dev in DEVICE_FIXTURE if dev.get("hostname")},
            {dev.get_unique_id() for dev in self.dna_center.get_all("device")},
        )
        self.dna_center.load_ports.assert_called()

    def test_load_devices_missing_location(self):
        """Validate handling of a Device when a Location is missing."""
        self.dna_center.building_map = {}
        self.dna_center.dnac_location_map = {}
        self.dna_center.load_devices()
        self.dna_center.job.logger.error.assert_called_with(
            "Device spine1.abc.in has unknown location in hierarchy so will not be imported."
        )

    def test_load_devices_missing_hostname(self):
        """Validate handling of a Device when hostname is missing."""
        device_fixture_no_hostname = [
            {
                "id": "12345",
                "managementIpAddress": "10.0.0.1",
                "serialNumber": "ABC123",
                "softwareType": "IOS",
                "hostname": None,
            }
        ]
        self.dna_center_client.get_devices.return_value = device_fixture_no_hostname
        self.dna_center.load_devices()
        self.dna_center.job.logger.warning.assert_called_with("Device 12345 is missing hostname so will be skipped.")
        self.assertEqual(len(self.dna_center.get_all("device")), 0)

    def test_load_ports(self):
        """Test Nautobot SSoT for Cisco DNA Center load_ports() function."""
        self.dna_center.load_devices()
        expected_ports = []
        for dev in DEVICE_FIXTURE:
            if dev.get("hostname"):
                for port in PORT_FIXTURE:
                    if port.get("portName"):
                        expected_ports.append(f"{port['portName']}__{dev['hostname']}")
        actual_ports = [port.get_unique_id() for port in self.dna_center.get_all("port")]
        self.assertEqual(expected_ports, actual_ports)

    def test_build_dnac_location_map_with_multi_level(self):
        """Test Nautobot adapter build_dnac_location_map method."""
        self.dna_center.dnac_location_map = {}
        self.dna_center.build_dnac_location_map(locations=MULTI_LEVEL_LOCATION_FIXTURE)
        self.assertEqual(self.dna_center.dnac_location_map, EXPECTED_DNAC_LOCATION_MAP_W_MULTI_LEVEL_LOCATIONS)
