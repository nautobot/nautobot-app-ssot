"""Test the DiffSync models for Nautobot."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import (
    Controller,
    ControllerManagedDeviceGroup,
    Device,
    DeviceType,
    Interface,
    Location,
    LocationType,
    Manufacturer,
    Platform,
)
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import IPAddress, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.dna_center.diffsync.models.nautobot import (
    NautobotArea,
    NautobotBuilding,
    NautobotDevice,
    NautobotFloor,
    NautobotIPAddressOnInterface,
)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_import_global": True}})
class TestNautobotArea(TestCase):
    """Test the NautobotArea class."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()
        cls.region_type = LocationType.objects.get_or_create(name="Region", nestable=True)[0]
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.area_loctype = cls.region_type
        cls.adapter.job.logger.info = MagicMock()
        cls.adapter.region_map = {}
        cls.adapter.locationtype_map = {"Region": cls.region_type.id}
        cls.adapter.status_map = {"Active": Status.objects.get(name="Active").id}

    def test_create(self):
        """Validate the NautobotArea create() method creates a Region."""
        status_active = Status.objects.get(name="Active")
        self.adapter.status_map = {"Active": status_active.id}
        global_region = Location.objects.create(name="Global", location_type=self.region_type, status=status_active)
        self.adapter.region_map = {None: {"Global": global_region.id}}
        ids = {"name": "NY", "parent": "Global", "parent_of_parent": None}
        attrs = {}
        result = NautobotArea.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotArea)
        self.adapter.job.logger.info.assert_called_once_with("Creating Region NY in Global.")
        region_obj = Location.objects.get(name=ids["name"], location_type__name="Region")
        self.assertEqual(region_obj.name, ids["name"])
        self.assertEqual(region_obj.parent.name, ids["parent"])

    def test_create_missing_parent(self):
        """Validate the NautobotArea create() method with missing parent Region."""
        ids = {"name": "TX", "parent": "USA"}
        attrs = {}
        NautobotArea.create(self.adapter, ids, attrs)
        self.adapter.job.logger.warning.assert_called_once_with("Unable to find Region USA in None for TX.")


@override_settings(
    PLUGINS_CONFIG={"nautobot_ssot": {"dna_center_delete_locations": True, "dna_center_update_locations": True}}
)
class TestNautobotBuilding(TestCase):
    """Test the NautobotBuilding class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()

        cls.reg_loc = LocationType.objects.get_or_create(name="Region", nestable=True)[0]
        loc_type, _ = LocationType.objects.update_or_create(name="Site", defaults={"parent": cls.reg_loc})
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = True
        cls.adapter.job.area_loctype = cls.reg_loc
        cls.adapter.job.building_loctype = loc_type
        cls.adapter.job.logger.info = MagicMock()
        cls.adapter.status_map = {"Active": Status.objects.get(name="Active").id}
        ga_tenant = Tenant.objects.create(name="G&A")
        cls.adapter.tenant_map = {"G&A": ga_tenant.id}
        ny_region = Location.objects.create(
            name="NY", location_type=cls.reg_loc, status=Status.objects.get(name="Active")
        )
        cls.adapter.locationtype_map = {"Region": cls.reg_loc.id, "Site": loc_type.id}
        cls.sec_site = Location.objects.create(
            name="Site 2", parent=ny_region, status=Status.objects.get(name="Active"), location_type=loc_type
        )
        cls.sec_site.validated_save()
        cls.adapter.site_map = {None: {"NY": ny_region.id}, "NY": {"Site 2": cls.sec_site.id}}
        cls.test_bldg = NautobotBuilding(
            name="Site 2",
            address="",
            area="NY",
            area_parent=None,
            latitude=0,
            longitude=0,
            tenant="G&A",
            uuid=cls.sec_site.id,
        )
        cls.test_bldg.adapter = cls.adapter

    def test_create(self):
        """Validate the NautobotBuilding create() method creates a Site."""
        ids = {"name": "HQ", "area": "NY"}
        attrs = {
            "address": "123 Main St",
            "area_parent": None,
            "latitude": 12.345,
            "longitude": -67.890,
            "tenant": "G&A",
        }
        ny_area = Location.objects.get_or_create(
            name="NY", location_type=LocationType.objects.get(name="Region"), status=Status.objects.get(name="Active")
        )[0]
        ny_area.validated_save()
        self.adapter.region_map = {None: {"NY": ny_area.id}}
        result = NautobotBuilding.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotBuilding)
        self.adapter.job.logger.info.assert_called_once_with("Creating Site HQ.")
        site_obj = Location.objects.get(name=ids["name"], location_type__name="Site")
        self.assertEqual(site_obj.name, ids["name"])
        self.assertEqual(site_obj.parent.name, ids["area"])
        self.assertEqual(site_obj.physical_address, attrs["address"])
        self.assertEqual(site_obj.tenant.name, attrs["tenant"])

    def test_update_w_tenant(self):
        """Validate the NautobotBuilding update() method updates a Site with a tenant."""
        update_attrs = {
            "address": "456 Wall St",
            "latitude": 23.456,
            "longitude": -78.901,
            "tenant": "G&A",
        }
        actual = NautobotBuilding.update(self=self.test_bldg, attrs=update_attrs)
        self.test_bldg.adapter.job.logger.info.assert_called_once_with("Updating Site Site 2.")
        self.sec_site.refresh_from_db()
        self.assertEqual(self.sec_site.physical_address, update_attrs["address"])
        self.assertEqual(float(self.sec_site.latitude), update_attrs["latitude"])
        self.assertEqual(float(self.sec_site.longitude), update_attrs["longitude"])
        self.assertEqual(self.sec_site.tenant.name, update_attrs["tenant"])
        self.assertEqual(actual, self.test_bldg)

    def test_update_wo_tenant(self):
        """Validate the NautobotBuilding update() method updates a Site without a tenant."""
        update_attrs = {
            "address": "456 Wall St",
            "latitude": 23.456,
            "longitude": -78.901,
            "tenant": "",
        }
        NautobotBuilding.update(self=self.test_bldg, attrs=update_attrs)
        self.sec_site.refresh_from_db()
        self.assertIsNone(self.sec_site.tenant)

    def test_delete(self):
        """Validate the NautobotBuilding delete() method deletes a Site."""
        ds_mock_site = MagicMock(spec=Location)
        ds_mock_site.location_type = "Site"
        ds_mock_site.uuid = "1234567890"
        ds_mock_site.adapter = MagicMock()
        ds_mock_site.adapter.job.building_loctype = self.adapter.job.building_loctype
        ds_mock_site.adapter.job.logger.info = MagicMock()
        mock_site = MagicMock(spec=Location)
        mock_site.name = "Test"
        site_get_mock = MagicMock(return_value=mock_site)
        with patch.object(Location.objects, "get", site_get_mock):
            result = NautobotBuilding.delete(ds_mock_site)
        ds_mock_site.adapter.job.logger.info.assert_called_once_with(
            f"Deleting {self.adapter.job.building_loctype.name} Test."
        )
        self.assertEqual(ds_mock_site, result)


class TestNautobotFloor(TestCase):
    """Test the NautobotFloor class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()

        site_loc_type = LocationType.objects.get_or_create(name="Site")[0]
        cls.floor_loc_type = LocationType.objects.get_or_create(name="Floor", parent=site_loc_type)[0]
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.building_loctype = site_loc_type
        cls.adapter.job.floor_loctype = cls.floor_loc_type
        cls.adapter.job.logger.info = MagicMock()
        ga_tenant = Tenant.objects.create(name="G&A")
        cls.adapter.tenant_map = {"G&A": ga_tenant.id}

        cls.adapter.locationtype_map = {"Site": site_loc_type.id, "Floor": cls.floor_loc_type.id}
        cls.hq_site, _ = Location.objects.get_or_create(
            name="HQ", location_type=site_loc_type, status=Status.objects.get(name="Active")
        )
        cls.adapter.site_map = {"NY": {"HQ": cls.hq_site.id}}
        cls.adapter.floor_map = {}
        cls.adapter.status_map = {"Active": Status.objects.get(name="Active").id}
        cls.adapter.objects_to_delete = {"floors": []}

    def test_create(self):
        """Test the NautobotFloor create() method creates a LocationType: Floor."""
        ids = {"name": "HQ - Floor 1", "building": "HQ", "area": "NY"}
        attrs = {"tenant": "G&A"}
        result = NautobotFloor.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotFloor)
        self.adapter.job.logger.info.assert_called_with("Creating Floor HQ - Floor 1.")
        floor_obj = Location.objects.get(name=ids["name"], location_type__name="Floor")
        self.assertEqual(floor_obj.name, ids["name"])
        self.assertEqual(floor_obj.parent.name, self.hq_site.name)
        self.assertEqual(floor_obj.tenant.name, attrs["tenant"])

    def test_update_w_tenant(self):
        """Test the NautobotFloor update() method updates a LocationType: Floor with tenant."""
        mock_floor = Location.objects.create(
            name="HQ - Floor 2",
            location_type=self.floor_loc_type,
            parent=self.hq_site,
            status=Status.objects.get(name="Active"),
        )
        mock_floor.validated_save()
        test_floor = NautobotFloor(name="HQ - Floor 2", building="HQ", area="NY", tenant="", uuid=mock_floor.id)
        test_floor.adapter = self.adapter
        update_attrs = {
            "tenant": "G&A",
        }
        actual = NautobotFloor.update(self=test_floor, attrs=update_attrs)
        test_floor.adapter.job.logger.info.assert_called_once_with("Updating Floor HQ - Floor 2 with {'tenant': 'G&A'}")
        mock_floor.refresh_from_db()
        self.assertEqual(mock_floor.tenant.name, update_attrs["tenant"])
        self.assertEqual(actual, test_floor)

    def test_update_wo_tenant(self):
        """Test the NautobotFloor update() method updates a LocationType: Floor without tenant."""
        # I hate having to duplicate with above method but we can't have in setUp and test for ContentTypes.
        mock_floor = Location.objects.create(
            name="HQ - Floor 2",
            location_type=self.floor_loc_type,
            parent=self.hq_site,
            status=Status.objects.get(name="Active"),
        )
        mock_floor.validated_save()
        test_floor = NautobotFloor(name="HQ - Floor 2", building="HQ", area="NY", tenant="", uuid=mock_floor.id)
        test_floor.adapter = self.adapter
        update_attrs = {
            "tenant": None,
        }
        NautobotFloor.update(self=test_floor, attrs=update_attrs)
        test_floor.adapter.job.logger.info.assert_called_once_with("Updating Floor HQ - Floor 2 with {'tenant': None}")
        mock_floor.refresh_from_db()
        self.assertIsNone(mock_floor.tenant)

    def test_delete(self):
        """Validate the NautobotFloor delete() method deletes a LocationType: Floor."""
        ds_mock_floor = MagicMock(spec=Location)
        ds_mock_floor.location_type = "Floor"
        ds_mock_floor.uuid = "1234567890"
        ds_mock_floor.adapter = self.adapter
        mock_floor = MagicMock(spec=Location)
        mock_floor.name = "Test"
        mock_floor.parent.name = "HQ"
        floor_get_mock = MagicMock(return_value=mock_floor)
        with patch.object(Location.objects, "get", floor_get_mock):
            result = NautobotFloor.delete(ds_mock_floor)
        ds_mock_floor.adapter.job.logger.info.assert_called_once_with(
            f"Deleting {self.adapter.job.floor_loctype.name} Test in HQ."
        )
        self.assertEqual(ds_mock_floor, result)


class TestNautobotDevice(TestCase):
    """Test NautobotDevice class."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()

        cls.status_active = Status.objects.get(name="Active")
        cls.site_lt = LocationType.objects.get_or_create(name="Site")[0]

        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.logger.info = MagicMock()
        cls.ga_tenant = Tenant.objects.create(name="G&A")
        cls.adapter.device_map = {}
        cls.adapter.floor_map = {}
        cls.adapter.site_map = {}
        ios_platform = Platform.objects.get_or_create(name="IOS", network_driver="cisco_ios")[0]
        cls.adapter.platform_map = {"cisco_ios": ios_platform.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.tenant_map = {"G&A": cls.ga_tenant.id}

        cls.hq_site = Location.objects.create(name="HQ", status=cls.status_active, location_type=cls.site_lt)

        dnac_controller = Controller.objects.get_or_create(
            name="DNA Center", status=cls.status_active, location=cls.hq_site
        )[0]
        dnac_group = ControllerManagedDeviceGroup.objects.create(
            name="DNA Center Managed Devices", controller=dnac_controller
        )
        cls.adapter.job.controller_group = dnac_group
        cls.adapter.job.dnac = dnac_controller

        cls.ids = {
            "name": "core-router.testexample.com",
        }
        cls.attrs = {
            "controller_group": "DNA Center Managed Devices",
            "floor": "HQ - Floor 1",
            "management_addr": "10.10.0.1",
            "model": "Nexus 9300",
            "platform": "cisco_ios",
            "role": "core",
            "area": "NY",
            "site": "HQ",
            "serial": "1234567890",
            "status": "Active",
            "tenant": "G&A",
            "vendor": "Cisco",
            "version": "16.12.3",
        }
        cls.adapter.objects_to_create = {"devices": [], "metadata": []}  # pylint: disable=no-member

    def test_create(self):
        """Test the NautobotDevice create() method creates a Device."""
        floor_lt = LocationType.objects.get_or_create(name="Floor", parent=self.site_lt)[0]
        hq_floor = Location.objects.create(name="HQ - Floor 1", status=self.status_active, location_type=floor_lt)
        self.adapter.site_map = {"NY": {"HQ": self.hq_site.id}}
        self.adapter.floor_map = {"NY": {"HQ": {"HQ - Floor 1": hq_floor.id}}}

        NautobotDevice.create(self.adapter, self.ids, self.attrs)
        self.adapter.job.logger.info.assert_called_with("Creating Device core-router.testexample.com.")
        new_dev = self.adapter.objects_to_create["devices"][0]
        self.assertEqual(new_dev.role, Role.objects.get(name=self.attrs["role"]))
        self.assertEqual(
            new_dev.device_type,
            DeviceType.objects.get(
                model=self.attrs["model"], manufacturer=Manufacturer.objects.get(name=self.attrs["vendor"])
            ),
        )
        self.assertEqual(new_dev.platform.network_driver, self.attrs["platform"])
        self.assertEqual(new_dev.serial, self.attrs["serial"])
        self.assertTrue(new_dev.location_id)
        self.assertEqual(new_dev.location_id, hq_floor.id)
        self.assertEqual(new_dev.tenant_id, self.ga_tenant.id)
        self.assertTrue(new_dev.software_version.version, self.attrs["version"])


class TestNautobotIPAddressOnInterface(TestCase):
    """Test NautobotIPAddressOnInterface class."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()

        cls.status_active = Status.objects.get(name="Active")
        cls.site_lt = LocationType.objects.get_or_create(name="Site")[0]

        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.objects_to_create = {"mappings": [], "primary_ip4": []}  # pylint: disable=no-member
        cls.ga_tenant = Tenant.objects.create(name="G&A")
        ios_platform = Platform.objects.get_or_create(name="IOS", network_driver="cisco_ios")[0]

        cls.hq_site = Location.objects.create(name="HQ", status=cls.status_active, location_type=cls.site_lt)

        dnac_controller = Controller.objects.get_or_create(
            name="DNA Center", status=cls.status_active, location=cls.hq_site
        )[0]
        dnac_group = ControllerManagedDeviceGroup.objects.create(
            name="DNA Center Managed Devices", controller=dnac_controller
        )
        cls.adapter.job.controller_group = dnac_group
        cls.adapter.job.dnac = dnac_controller

        test_device = Device.objects.create(
            name="core-router.testexample.com",
            status=cls.status_active,
            location=cls.hq_site,
            device_type=DeviceType.objects.get_or_create(
                model="Nexus 9300", manufacturer=Manufacturer.objects.get_or_create(name="Cisco")[0]
            )[0],
            platform=ios_platform,
            role=Role.objects.get_or_create(name="core")[0],
            serial="1234567890",
            tenant=cls.ga_tenant,
            controller_managed_device_group=dnac_group,
        )
        cls.adapter.device_map = {"core-router.testexample.com": test_device.id}
        mgmt_intf = Interface.objects.create(
            name="mgmt0",
            device=test_device,
            status=cls.status_active,
            type="virtual",
            enabled=True,
            mac_address="00:11:22:33:44:55",
        )
        cls.adapter.port_map = {"core-router.testexample.com": {"mgmt0": mgmt_intf.id}}
        parent_pf = Prefix.objects.create(
            prefix="10.1.1.0/24",
            status=cls.status_active,
        )
        mgmt_ip = IPAddress.objects.create(
            host="10.1.1.1",
            mask_length=24,
            parent=parent_pf,
            status=cls.status_active,
            tenant=cls.ga_tenant,
        )
        cls.adapter.ipaddr_map = {"10.1.1.1": mgmt_ip.id}

    def test_create(self):
        """Test the NautobotIPAddressOnInterface create() method creates an IPAddress on an Interface."""
        ids = {
            "host": "10.1.1.1",
            "device": "core-router.testexample.com",
            "port": "mgmt0",
        }
        attrs = {
            "primary": True,
        }
        results = NautobotIPAddressOnInterface.create(self.adapter, ids, attrs)
        self.assertIsInstance(results, NautobotIPAddressOnInterface)
        self.assertEqual(len(self.adapter.objects_to_create["mappings"]), 1)
        new_map = self.adapter.objects_to_create["mappings"][0]
        self.assertEqual(new_map.ip_address.host, ids["host"])
        self.assertEqual(new_map.interface.name, ids["port"])
