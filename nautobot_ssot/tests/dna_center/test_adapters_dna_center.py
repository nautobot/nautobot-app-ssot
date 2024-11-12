"""Test DNA Center adapter."""

import uuid
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
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
    EXPECTED_AREAS,
    EXPECTED_AREAS_WO_GLOBAL,
    EXPECTED_BUILDINGS,
    EXPECTED_DNAC_LOCATION_MAP,
    EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL,
    EXPECTED_FLOORS,
    LOCATION_FIXTURE,
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

    def test_build_dnac_location_map(self):
        """Test Nautobot adapter build_dnac_location_map method."""
        self.dna_center.dnac_location_map = {}
        actual = self.dna_center.build_dnac_location_map(locations=LOCATION_FIXTURE)
        expected = EXPECTED_DNAC_LOCATION_MAP
        self.assertEqual(sorted(actual), sorted(expected))

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_import_global": False}})
    def test_build_dnac_location_map_wo_global(self):
        """Test Nautobot adapter build_dnac_location_map method without global."""
        self.dna_center.dnac_location_map = {}
        actual = self.dna_center.build_dnac_location_map(locations=LOCATION_FIXTURE)
        expected = EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL
        self.assertEqual(sorted(actual), sorted(expected))

    def test_parse_and_sort_locations(self):
        """Test Nautobot adapter parse_and_sort_locations method."""
        actual_areas, actual_buildings, actual_floors = self.dna_center.parse_and_sort_locations(
            locations=LOCATION_FIXTURE
        )
        self.assertEqual(actual_areas, EXPECTED_AREAS)
        self.assertEqual(actual_buildings, EXPECTED_BUILDINGS)
        self.assertEqual(actual_floors, EXPECTED_FLOORS)

    def test_load_locations_success(self):
        """Test Nautobot SSoT for Cisco DNA Center load_locations() function successfully."""
        self.dna_center.load_buildings = MagicMock()
        self.dna_center.load_floors = MagicMock()
        self.dna_center_client.get_location.return_value = [{"name": "NY"}]
        self.dna_center.load_locations()
        self.dna_center_client.get_locations.assert_called()
        self.dna_center.load_buildings.assert_called_once()
        self.dna_center.load_floors.assert_called_once()

    def test_load_locations_failure(self):
        """Test Nautobot SSoT for Cisco DNA Center load_locations() function fails."""
        self.dna_center_client.get_locations.return_value = []
        self.dna_center.load_locations()
        self.dna_center.job.logger.error.assert_called_once_with(
            "No location data was returned from DNAC. Unable to proceed."
        )

    def test_load_area_w_global(self):
        """Test Nautobot SSoT for Cisco DNA Center load_area() function with Global area."""
        for area in EXPECTED_AREAS:
            hierarchy = area["siteNameHierarchy"].split("/")
            if isinstance(hierarchy, list) and len(hierarchy) > 1:
                self.dna_center.load_area(area=hierarchy[-1], area_parent=hierarchy[-2])
            else:
                self.dna_center.load_area(area=hierarchy[0])
        area_expected = sorted(
            [f"{x['name']}__{x['parent']}" for x in EXPECTED_DNAC_LOCATION_MAP.values() if x["loc_type"] == "area"]
        )
        area_actual = sorted([area.get_unique_id() for area in self.dna_center.get_all("area")])
        self.assertEqual(area_actual, area_expected)

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_import_global": False}})
    def test_load_area_wo_global(self):
        """Test Nautobot SSoT for Cisco DNA Center load_area() function without Global area."""
        self.dna_center.dnac_location_map = EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL
        for area in EXPECTED_AREAS_WO_GLOBAL:
            hierarchy = area["siteNameHierarchy"].split("/")
            if hierarchy[-2] == "Global":
                area_parent = None
            else:
                area_parent = hierarchy[-2]
            self.dna_center.load_area(area=hierarchy[-1], area_parent=area_parent)
        area_expected = [
            f"{x['name']}__{x['parent']}"
            for x in EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL.values()
            if x["loc_type"] == "area"
        ]
        area_actual = [area.get_unique_id() for area in self.dna_center.get_all("area")]
        self.assertEqual(sorted(area_actual), sorted(area_expected))

    def test_load_buildings_w_global(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function with Global area."""
        self.dna_center_client.find_address_and_type.side_effect = [
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
        ]
        self.dna_center.load_buildings(buildings=EXPECTED_BUILDINGS)
        building_expected = [
            f"{x['name']}__{x['parent']}" for x in EXPECTED_DNAC_LOCATION_MAP.values() if x["loc_type"] == "building"
        ]
        building_actual = [building.get_unique_id() for building in self.dna_center.get_all("building")]
        self.assertEqual(building_actual, building_expected)

    def test_load_buildings_wo_global(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function without Global area."""
        self.dna_center_client.find_address_and_type.side_effect = [
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
        ]
        self.dna_center.dnac_location_map = EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL
        self.dna_center.load_buildings(buildings=EXPECTED_BUILDINGS)
        building_expected = [
            f"{x['name']}__{x['parent']}"
            for x in EXPECTED_DNAC_LOCATION_MAP_WO_GLOBAL.values()
            if x["loc_type"] == "building"
        ]
        building_actual = [building.get_unique_id() for building in self.dna_center.get_all("building")]
        self.assertEqual(sorted(building_actual), sorted(building_expected))

    def test_load_buildings_duplicate(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function with duplicate building."""
        self.dna_center.load_area = MagicMock()
        self.dna_center_client.find_address_and_type.side_effect = [
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
            ("", "building"),
        ]
        self.dna_center.load_buildings(buildings=EXPECTED_BUILDINGS)
        self.dna_center.load_buildings(buildings=[EXPECTED_BUILDINGS[0]])
        self.dna_center.job.logger.warning.assert_called_with("Site Building1 already loaded so skipping.")

    def test_load_buildings_w_location_map_building_change(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function with Job location_map and building data."""
        self.job.location_map = {"Rome": {"parent": "Italy", "area_parent": "Europe"}}
        self.dna_center_client.find_address_and_type.side_effect = [("", "building")]

        self.dna_center.load_area = MagicMock()
        self.dna_center.load_buildings(buildings=[EXPECTED_BUILDINGS[7]])
        self.dna_center.load_area.assert_called_with(area="Italy", area_parent="Europe")
        loaded_bldg = self.dna_center.get("building", {"name": "Rome", "area": "Italy"})
        self.assertEqual(loaded_bldg.name, "Rome")
        self.assertEqual(loaded_bldg.area, "Italy")
        self.assertEqual(loaded_bldg.area_parent, "Europe")

    def test_load_buildings_w_location_map_area_change(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function with Job location_map and area data."""
        self.job.location_map = {"SanDiego": {"parent": "California"}}
        self.dna_center_client.find_address_and_type.side_effect = [("", "building")]

        self.dna_center.load_area = MagicMock()
        self.dna_center.load_buildings(buildings=[EXPECTED_BUILDINGS[5]])
        self.dna_center.load_area.assert_called_with(area="SanDiego", area_parent="California")
        loaded_bldg = self.dna_center.get("building", {"name": "1", "area": "SanDiego"})
        self.assertEqual(loaded_bldg.name, "1")
        self.assertEqual(loaded_bldg.area, "SanDiego")
        self.assertEqual(loaded_bldg.area_parent, "California")

    def test_load_buildings_w_location_map_area_and_bldg_change(self):
        """Test Nautobot SSoT for Cisco DNA Center load_buildings() function with Job location_map and area and building data."""
        self.job.location_map = {"HQ": {"parent": "New York", "area_parent": "USA"}, "New York": {"parent": "New York"}}
        self.dna_center_client.find_address_and_type.side_effect = [("", "building")]

        self.dna_center.load_area = MagicMock()
        test_bldg = [
            {
                "parentId": "04509ce4-6c88-40a3-b444-9e00f2cd97f2",
                "additionalInfo": [
                    {
                        "nameSpace": "Location",
                        "attributes": {
                            "latitude": "39.156233",
                            "type": "building",
                            "longitude": "-74.690192",
                        },
                    }
                ],
                "name": "HQ",
                "id": "2d0d8545-b6de-4dda-a0f7-93bcd7d0e738",
                "siteHierarchy": "9e5f9fc2-032e-45e8-994c-4a00629648e8/04509ce4-6c88-40a3-b444-9e00f2cd97f2/2d0d8545-b6de-4dda-a0f7-93bcd7d0e738",
                "siteNameHierarchy": "Global/SanDiego/HQ",
            }
        ]
        self.dna_center.load_buildings(buildings=test_bldg)
        self.dna_center.load_area.assert_called_with(area="New York", area_parent="USA")
        loaded_bldg = self.dna_center.get("building", {"name": "HQ", "area": "New York"})
        self.assertEqual(loaded_bldg.name, "HQ")
        self.assertEqual(loaded_bldg.area, "New York")
        self.assertEqual(loaded_bldg.area_parent, "USA")

    def test_load_floors(self):
        """Test Nautobot SSoT for Cisco DNA Center load_floors() function."""
        self.job.location_map = {}
        self.dna_center.get = MagicMock()
        self.dna_center.load_floors(floors=EXPECTED_FLOORS)
        floor_expected = [
            "Building1 - Floor1__Building1",
            "1 - 1__1",
            "Deep Space - 1st Floor__Deep Space",
            "Building 1 - Lab__Building 1",
            "secretlab - Floor 2__secretlab",
        ]
        floor_actual = [floor.get_unique_id() for floor in self.dna_center.get_all("floor")]
        self.assertEqual(floor_actual, floor_expected)

    def test_load_floors_missing_parent(self):
        """Test Nautobot SSoT for Cisco DNA Center load_floors() function with missing parent."""
        self.dna_center.dnac_location_map = {}
        self.dna_center.load_floors(floors=EXPECTED_FLOORS)
        self.dna_center.job.logger.warning.assert_called_with("Parent to Floor 2 can't be found so will be skipped.")

    def test_load_devices(self):
        """Test Nautobot SSoT for Cisco DNA Center load_devices() function."""
        self.dna_center.load_ports = MagicMock()
        self.dna_center.load_devices()
        self.assertEqual(
            {f"{dev['hostname']}" for dev in DEVICE_FIXTURE if dev.get("hostname")},
            {dev.get_unique_id() for dev in self.dna_center.get_all("device")},
        )
        self.dna_center.load_ports.assert_called()

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

    def test_load_ports_validation_error(self):
        """Test Nautobot SSoT for Cisco DNA Center load_ports() function throwing ValidationError."""
        self.dna_center.add = MagicMock(side_effect=ValidationError(message="leaf3.abc.inc not found"))
        mock_device = MagicMock()
        mock_device.name = "leaf3.abc.inc"
        self.dna_center.load_ports(device_id="1234567890", dev=mock_device)
        self.dna_center.job.logger.warning.assert_called_with(
            "Unable to load port Vlan848 for leaf3.abc.inc. ['leaf3.abc.inc not found']"
        )
