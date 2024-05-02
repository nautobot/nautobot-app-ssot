"""Test the DiffSync models for Nautobot."""

from unittest.mock import MagicMock, patch
from diffsync import DiffSync
from nautobot.dcim.models import (
    Location,
    LocationType,
    DeviceType,
    Manufacturer,
)
from nautobot.extras.models import Status, Role
from nautobot.tenancy.models import Tenant
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot_dna_center.diffsync.models.nautobot import (
    NautobotArea,
    NautobotBuilding,
    NautobotFloor,
    NautobotDevice,
)


class TestNautobotArea(TransactionTestCase):
    """Test the NautobotArea class."""

    def setUp(self):
        super().setUp()
        self.diffsync = DiffSync()
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()
        self.diffsync.region_map = {}
        self.region_type = LocationType.objects.get(name="Region")
        self.diffsync.locationtype_map = {"Region": self.region_type.id}
        self.diffsync.status_map = {"Active": Status.objects.get(name="Active").id}

    def test_create(self):
        """Validate the NautobotArea create() method creates a Region."""
        status_active = Status.objects.get(name="Active")
        self.diffsync.status_map = {"Active": status_active.id}
        global_region = Location.objects.create(name="Global", location_type=self.region_type, status=status_active)
        self.diffsync.region_map = {"Global": global_region.id}
        ids = {"name": "NY", "parent": "Global"}
        attrs = {}
        result = NautobotArea.create(self.diffsync, ids, attrs)
        self.assertIsInstance(result, NautobotArea)
        self.diffsync.job.logger.info.assert_called_once_with("Creating Region NY.")
        region_obj = Location.objects.get(name=ids["name"], location_type__name="Region")
        self.assertEqual(region_obj.name, ids["name"])
        self.assertEqual(region_obj.parent.name, ids["parent"])

    def test_create_missing_parent(self):
        """Validate the NautobotArea create() method with missing parent Region."""
        ids = {"name": "TX", "parent": "USA"}
        attrs = {}
        NautobotArea.create(self.diffsync, ids, attrs)
        self.diffsync.job.logger.warning.assert_called_once_with("Unable to find Region USA for TX.")


class TestNautobotBuilding(TransactionTestCase):
    """Test the NautobotBuilding class."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()

        self.diffsync = DiffSync()
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()
        self.diffsync.status_map = {"Active": Status.objects.get(name="Active").id}
        ga_tenant = Tenant.objects.create(name="G&A")
        self.diffsync.tenant_map = {"G&A": ga_tenant.id}
        reg_loc = LocationType.objects.get(name="Region")
        ny_region = Location.objects.create(name="NY", location_type=reg_loc, status=Status.objects.get(name="Active"))
        loc_type = LocationType.objects.get(name="Site")
        self.diffsync.locationtype_map = {"Region": reg_loc.id, "Site": loc_type.id}
        self.sec_site = Location.objects.create(
            name="Site 2", parent=ny_region, status=Status.objects.get(name="Active"), location_type=loc_type
        )
        self.sec_site.validated_save()
        self.diffsync.site_map = {"NY": ny_region.id, "Site 2": self.sec_site.id}
        self.test_bldg = NautobotBuilding(
            name="Site 2", address="", area="NY", latitude="", longitude="", tenant="G&A", uuid=self.sec_site.id
        )
        self.test_bldg.diffsync = self.diffsync

    def test_create(self):
        """Validate the NautobotBuilding create() method creates a Site."""
        ids = {"name": "HQ"}
        attrs = {"address": "123 Main St", "area": "NY", "latitude": "12.345", "longitude": "-67.890", "tenant": "G&A"}
        ny_area = Location.objects.get_or_create(
            name="NY", location_type=LocationType.objects.get(name="Region"), status=Status.objects.get(name="Active")
        )[0]
        ny_area.validated_save()
        self.diffsync.region_map = {"NY": ny_area.id}
        result = NautobotBuilding.create(self.diffsync, ids, attrs)
        self.assertIsInstance(result, NautobotBuilding)
        self.diffsync.job.logger.info.assert_called_once_with("Creating Site HQ.")
        site_obj = Location.objects.get(name=ids["name"], location_type__name="Site")
        self.assertEqual(site_obj.name, ids["name"])
        self.assertEqual(site_obj.parent.name, attrs["area"])
        self.assertEqual(site_obj.physical_address, attrs["address"])
        self.assertEqual(site_obj.tenant.name, attrs["tenant"])

    def test_update_w_tenant(self):
        """Validate the NautobotBuilding update() method updates a Site with a tenant."""
        update_attrs = {
            "address": "456 Wall St",
            "latitude": "23.456",
            "longitude": "-78.901",
            "tenant": "G&A",
        }
        actual = NautobotBuilding.update(self=self.test_bldg, attrs=update_attrs)
        self.test_bldg.diffsync.job.logger.info.assert_called_once_with("Updating Site Site 2.")
        self.sec_site.refresh_from_db()
        self.assertEqual(self.sec_site.physical_address, update_attrs["address"])
        self.assertEqual(str(self.sec_site.latitude).rstrip("0"), update_attrs["latitude"])
        self.assertEqual(f"{self.sec_site.longitude:.3f}", update_attrs["longitude"])
        self.assertEqual(self.sec_site.tenant.name, update_attrs["tenant"])
        self.assertEqual(actual, self.test_bldg)

    def test_update_wo_tenant(self):
        """Validate the NautobotBuilding update() method updates a Site without a tenant."""
        update_attrs = {
            "address": "456 Wall St",
            "latitude": "23.456",
            "longitude": "-78.901",
            "tenant": "",
        }
        NautobotBuilding.update(self=self.test_bldg, attrs=update_attrs)
        self.sec_site.refresh_from_db()
        self.assertIsNone(self.sec_site.tenant)

    def test_delete(self):
        """Validate the NautobotBuilding delete() method deletes a Site."""
        ds_mock_site = MagicMock(spec=Location)
        ds_mock_site.uuid = "1234567890"
        ds_mock_site.diffsync = MagicMock()
        ds_mock_site.diffsync.job.logger.info = MagicMock()
        mock_site = MagicMock(spec=Location)
        mock_site.name = "Test"
        site_get_mock = MagicMock(return_value=mock_site)
        with patch.object(Location.objects, "get", site_get_mock):
            result = NautobotBuilding.delete(ds_mock_site)
        ds_mock_site.diffsync.job.logger.info.assert_called_once_with("Deleting Site Test.")
        self.assertEqual(ds_mock_site, result)


class TestNautobotFloor(TransactionTestCase):
    """Test the NautobotFloor class."""

    databases = ("default", "job_logs")

    def setUp(self):
        super().setUp()

        self.diffsync = DiffSync()
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()
        ga_tenant = Tenant.objects.create(name="G&A")
        self.diffsync.tenant_map = {"G&A": ga_tenant.id}
        loc_type = LocationType.objects.get(name="Site")
        self.diffsync.locationtype_map = {"Site": loc_type.id, "Floor": LocationType.objects.get(name="Floor").id}
        self.hq_site, _ = Location.objects.get_or_create(
            name="HQ", location_type=loc_type, status=Status.objects.get(name="Active")
        )
        self.diffsync.site_map = {"HQ": self.hq_site.id}
        self.diffsync.floor_map = {}
        self.diffsync.status_map = {"Active": Status.objects.get(name="Active").id}

    def test_create(self):
        """Test the NautobotFloor create() method creates a LocationType: Floor."""
        ids = {"name": "HQ - Floor 1", "building": "HQ"}
        attrs = {"tenant": "G&A"}
        result = NautobotFloor.create(self.diffsync, ids, attrs)
        self.assertIsInstance(result, NautobotFloor)
        self.diffsync.job.logger.info.assert_called_with("Creating Floor HQ - Floor 1.")
        floor_obj = Location.objects.get(name=ids["name"], location_type__name="Floor")
        self.assertEqual(floor_obj.name, ids["name"])
        self.assertEqual(floor_obj.parent.name, self.hq_site.name)
        self.assertEqual(floor_obj.tenant.name, attrs["tenant"])

    def test_update_w_tenant(self):
        """Test the NautobotFloor update() method updates a LocationType: Floor with tenant."""
        floor_type = LocationType.objects.get(name="Floor")
        mock_floor = Location.objects.create(
            name="HQ - Floor 2",
            location_type=floor_type,
            parent=self.hq_site,
            status=Status.objects.get(name="Active"),
        )
        mock_floor.validated_save()
        test_floor = NautobotFloor(name="HQ - Floor 2", building="HQ", tenant="", uuid=mock_floor.id)
        test_floor.diffsync = self.diffsync
        update_attrs = {
            "tenant": "G&A",
        }
        actual = NautobotFloor.update(self=test_floor, attrs=update_attrs)
        test_floor.diffsync.job.logger.info.assert_called_once_with(
            "Updating Floor HQ - Floor 2 with {'tenant': 'G&A'}"
        )
        mock_floor.refresh_from_db()
        self.assertEqual(mock_floor.tenant.name, update_attrs["tenant"])
        self.assertEqual(actual, test_floor)

    def test_update_wo_tenant(self):
        """Test the NautobotFloor update() method updates a LocationType: Floor without tenant."""
        # I hate having to duplicate with above method but we can't have in setUp and test for ContentTypes.
        floor_type, _ = LocationType.objects.get_or_create(name="Floor")
        mock_floor = Location.objects.create(
            name="HQ - Floor 2",
            location_type=floor_type,
            parent=self.hq_site,
            status=Status.objects.get(name="Active"),
        )
        mock_floor.validated_save()
        test_floor = NautobotFloor(name="HQ - Floor 2", building="HQ", tenant="", uuid=mock_floor.id)
        test_floor.diffsync = MagicMock()
        test_floor.diffsync.job.logger.info = MagicMock()
        update_attrs = {
            "tenant": None,
        }
        NautobotFloor.update(self=test_floor, attrs=update_attrs)
        test_floor.diffsync.job.logger.info.assert_called_once_with("Updating Floor HQ - Floor 2 with {'tenant': None}")
        mock_floor.refresh_from_db()
        self.assertIsNone(mock_floor.tenant)

    def test_delete(self):
        """Validate the NautobotFloor delete() method deletes a LocationType: Floor."""
        ds_mock_floor = MagicMock(spec=Location)
        ds_mock_floor.uuid = "1234567890"
        ds_mock_floor.diffsync = MagicMock()
        ds_mock_floor.diffsync.job.logger.info = MagicMock()
        mock_floor = MagicMock(spec=Location)
        mock_floor.name = "Test"
        mock_floor.parent.name = "HQ"
        floor_get_mock = MagicMock(return_value=mock_floor)
        with patch.object(Location.objects, "get", floor_get_mock):
            result = NautobotFloor.delete(ds_mock_floor)
        ds_mock_floor.diffsync.job.logger.info.assert_called_once_with("Deleting Floor Test in HQ.")
        self.assertEqual(ds_mock_floor, result)


class TestNautobotDevice(TransactionTestCase):
    """Test NautobotDevice class."""

    def setUp(self):
        super().setUp()

        self.diffsync = DiffSync()
        self.diffsync.job = MagicMock()
        self.diffsync.job.logger.info = MagicMock()
        self.ga_tenant = Tenant.objects.create(name="G&A")
        self.diffsync.tenant_map = {"G&A": self.ga_tenant.id}

        self.status_active = Status.objects.get(name="Active")
        self.diffsync.status_map = {"Active": self.status_active.id}
        self.ids = {
            "name": "core-router.testexample.com",
        }
        self.attrs = {
            "floor": "HQ - Floor 1",
            "management_addr": "10.10.0.1",
            "model": "Nexus 9300",
            "platform": "cisco_ios",
            "role": "core",
            "site": "HQ",
            "serial": "1234567890",
            "status": "Active",
            "tenant": "G&A",
            "vendor": "Cisco",
            "version": "16.12.3",
        }
        self.diffsync.site_map = {}
        self.diffsync.floor_map = {}
        self.diffsync.device_map = {}
        self.diffsync.objects_to_create = {"devices": []}  # pylint: disable=no-member

    @patch("nautobot_ssot_dna_center.diffsync.models.nautobot.LIFECYCLE_MGMT", True)
    def test_create(self):
        """Test the NautobotDevice create() method creates a Device."""
        hq_site = Location.objects.create(
            name="HQ", status=self.status_active, location_type=LocationType.objects.get(name="Site")
        )
        hq_floor = Location.objects.create(
            name="HQ - Floor 1", status=self.status_active, location_type=LocationType.objects.get(name="Floor")
        )
        self.diffsync.site_map = {"HQ": hq_site.id}
        self.diffsync.floor_map = {"HQ - Floor 1": hq_floor.id}

        NautobotDevice.create(self.diffsync, self.ids, self.attrs)
        self.diffsync.job.logger.info.assert_called_with("Creating Version 16.12.3 for cisco_ios.")
        new_dev = self.diffsync.objects_to_create["devices"][0]
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
        self.assertTrue(new_dev.custom_field_data["os_version"], self.attrs["version"])
