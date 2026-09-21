# pylint: disable=too-many-lines
"""Test Nautobot Utilities."""

import unittest
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from nautobot.apps.change_logging import JobChangeContext, change_logging
from nautobot.apps.testing import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import DeviceType, Interface, Location, LocationType, Manufacturer, Platform, VirtualChassis
from nautobot.dcim.models.devices import Device
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import CustomField, Role, Tag
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import VLAN, IPAddress, Prefix, get_default_namespace

from nautobot_ssot.integrations.ipfabric.bulk_writes import PendingWrites
from nautobot_ssot.integrations.ipfabric.constants import LAST_SYNCHRONIZED_CF_NAME
from nautobot_ssot.integrations.ipfabric.utilities import (
    assign_device_to_virtual_chassis,
    create_interface,
    create_ip,
    create_vlan,
    get_device_role_object,
    get_device_type_object,
    get_location_object,
    get_manufacturer_object,
    get_or_create_device_role_object,
    get_or_create_device_type_object,
    get_or_create_location_object,
    get_or_create_manufacturer_object,
    get_or_create_platform_object,
    get_or_create_status_object,
    get_or_create_tag_object,
    get_or_create_virtual_chassis_object,
    get_platform_object,
    get_syncable_device,
    get_virtual_chassis_object,
)
from nautobot_ssot.integrations.ipfabric.utilities.nbutils import (
    IPAddressToInterface,
    create_parent_prefix,
    deferred_change_logging,
    get_tagged_interface,
    queue_ip,
    tag_object,
)
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache


# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-public-methods
class TestNautobotUtils(TestCase):
    """Test Nautobot Utility."""

    def setUp(self):
        """Setup."""
        populate_status_choices()
        job_scoped_cache.clear_all()
        site_location_type = LocationType.objects.update_or_create(name="Site")[0]
        locaiton_cts = [
            ContentType.objects.get_for_model(VLAN),
            ContentType.objects.get_for_model(Device),
        ]
        site_location_type.content_types.set(locaiton_cts)
        self.location = Location.objects.create(
            name="Test-Location",
            status=Status.objects.get(name="Active"),
            location_type=site_location_type,
        )

        status_active = Status.objects.get(name="Active")

        self.manufacturer = Manufacturer.objects.create(name="Test-Manufacturer")
        self.device_type = DeviceType.objects.create(model="Test-DeviceType", manufacturer=self.manufacturer)
        self.content_type = ContentType.objects.get_for_model(Device)
        self.device_role = Role.objects.create(name="Test-Role", color=ColorChoices.COLOR_RED)
        self.device_role.content_types.set([self.content_type])
        self.device_role.cf["ipfabric_type"] = "Test-Role"
        self.device_role.validated_save()
        self.status = Status.objects.create(
            name="Test-Status",
            color=ColorChoices.COLOR_AMBER,
            description="Test-Description",
        )
        self.status.content_types.set([self.content_type])
        self.prefix = Prefix.objects.get_or_create(
            prefix="192.168.0.0/16", namespace=get_default_namespace(), status=status_active
        )[0]
        self.ip_address = IPAddress.objects.create(address="192.168.0.1/32", status=status_active, parent=self.prefix)

        self.device = Device.objects.create(
            name="Test-Device",
            location=self.location,
            device_type=self.device_type,
            role=self.device_role,
            status=status_active,
        )

        self.device.interfaces.create(name="Test-Interface", status=status_active)
        self.vlan_content_type = ContentType.objects.get(app_label="ipam", model="vlan")
        self.vlan_status = Status.objects.create(
            name="Test-Vlan-Status",
            color=ColorChoices.COLOR_AMBER,
            description="Test-Description",
        )
        self.vlan_status.content_types.set([self.vlan_content_type])

    def test_create_vlan(self):
        """Test `create_vlan` Utility."""
        vlan = create_vlan(
            vlan_name="Test-Vlan",
            vlan_id=100,
            vlan_status="Test-Vlan-Status",
            location_obj=self.location,
            description="Test-Vlan",
        )
        self.assertEqual(VLAN.objects.get(name="Test-Vlan").pk, vlan.pk)

    def test_create_location_existing_location_no_location_id(self):
        """Test `create_location` Utility."""
        test_location = get_or_create_location_object(location_name="Test-Location")
        self.assertEqual(test_location.id, self.location.id)

    def test_create_location_existing_location_with_location_id(self):
        """The site id reaches the database, not just the instance handed back."""
        self.assertFalse(self.location.cf.get("ipfabric_site_id"))
        test_location = get_or_create_location_object(location_name="Test-Location", location_id="Test-Location")
        self.assertEqual(test_location.id, self.location.id)
        self.assertEqual(test_location.cf["ipfabric_site_id"], "Test-Location")
        self.location.refresh_from_db()
        self.assertEqual(self.location.cf["ipfabric_site_id"], "Test-Location")

    def test_create_location_no_location_id(self):
        """Test `create_location` Utility."""
        test_location = get_or_create_location_object(location_name="Test-Location-new")
        self.assertEqual(test_location.name, "Test-Location-new")

    def test_create_location_with_location_id(self):
        """Test `create_location` Utility."""
        self.assertFalse(Location.objects.filter(name="Test-Location-new"))
        test_location = get_or_create_location_object(
            location_name="Test-Location-new", location_id="Test-Location-new"
        )
        self.assertEqual(test_location.name, "Test-Location-new")
        self.assertEqual(test_location.cf["ipfabric_site_id"], "Test-Location-new")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_multiple_locations_returned(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [Location.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        test_location = get_or_create_location_object(
            location_name="Test-Location", location_id="Test-Location", logger=logger
        )
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Multiple Locations returned with name Test-Location")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_db_error(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_location = get_or_create_location_object(
            location_name="Test-Location", location_id="Test-Location", logger=logger
        )
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Unable to create a new Location named Test-Location with LocationType Site")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_validation_error(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_location = get_or_create_location_object(
            location_name="Test-Location", location_id="Test-Location", logger=logger
        )
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Unable to create a new Location named Test-Location with LocationType Site")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_tag_db_error(self, mock_logger, mock_tag_object):
        """That save is a new Location's only one, so a refused one leaves no Location to return."""
        mock_tag_object.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_or_create_location_object(location_name="Test-Location-new", logger=logger))
        self.assertFalse(Location.objects.filter(name="Test-Location-new").exists())
        self.assertIn(
            "Unable to perform a validated_save() on Location Test-Location-new",
            logger.warning.call_args.args[0],
        )

    def test_get_location_object_returns_an_existing_location(self):
        """The lookup used when Locations are out of scope finds one another App may have created."""
        existing = get_or_create_location_object(location_name="Test-Location")
        self.assertEqual(get_location_object("Test-Location"), existing)

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_location_object_returns_none_when_absent(self, mock_logger):
        """A missing Location is not an error here; it is expected to arrive from another App."""
        logger = mock_logger("nb_job")
        self.assertIsNone(get_location_object("Test-Location-absent", logger=logger))
        logger.error.assert_not_called()

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_location_object_multiple_returned(self, mock_logger, mock_get):
        """Two Locations sharing a name cannot be told apart, so neither is used."""
        mock_get.side_effect = [Location.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_location_object("Test-Location", logger=logger))
        logger.error.assert_called_with("Multiple Locations returned with name Test-Location")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_tag_validation_error(self, mock_logger, mock_tag_object):
        """A refused validation leaves the new Location unwritten, as a refused insert does."""
        mock_tag_object.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_or_create_location_object(location_name="Test-Location-new", logger=logger))
        self.assertFalse(Location.objects.filter(name="Test-Location-new").exists())
        self.assertIn(
            "Unable to perform a validated_save() on Location Test-Location-new",
            logger.warning.call_args.args[0],
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_tag_error_keeps_an_existing_location(self, mock_logger, mock_restamp):
        """A Location that was already there keeps its row, so a failed re-stamp does not withhold it."""
        mock_restamp.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_location = get_or_create_location_object(location_name="Test-Location", logger=logger)
        self.assertEqual(test_location.id, self.location.id)
        self.assertIn(
            "Unable to perform a validated_save() on Location Test-Location",
            logger.warning.call_args.args[0],
        )

    def test_get_or_create_device_type_object(self):
        """Test `create_device_type_object` Utility."""
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType-New", vendor_name="Test-Manufacturer"
        )
        self.assertEqual(test_device_type.model, "Test-DeviceType-New")

    def test_create_device_type_object_existing_device_type(self):
        """Test `create_device_type_object` Utility."""
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType", vendor_name="Test-Manufacturer"
        )
        self.assertEqual(test_device_type.id, self.device_type.id)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.get_or_create_manufacturer_object", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_fail_to_get_manufacturer(
        self, mock_logger, mock_device_type, mock_get_or_create_manufacturer_object
    ):
        """Test `create_device_type_object` Utility."""
        mock_get_or_create_manufacturer_object.return_value = None
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType", vendor_name="Test-Manufacturer", logger=logger
        )
        mock_device_type.assert_not_called()
        logger.warning.assert_called_with(
            "Unable to get or create a Manufacturer named Test-Manufacturer, and therefore cannot create a DeviceType Test-DeviceType"
        )
        self.assertEqual(test_device_type, None)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_multiple_device_types_returned(self, mock_logger, mock_device_type):
        """Test `create_device_type_object` Utility."""
        mock_device_type.side_effect = [DeviceType.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType", vendor_name="Test-Manufacturer", logger=logger
        )
        logger.error.assert_called_with(
            "Multiple DeviceTypes returned with name Test-DeviceType and Manufacturer name Test-Manufacturer"
        )
        self.assertEqual(test_device_type, None)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_db_error(self, mock_logger, mock_device_type):
        """Test `create_device_type_object` Utility."""
        mock_device_type.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType", vendor_name="Test-Manufacturer", logger=logger
        )
        logger.error.assert_called_with(
            "Unable to create a new DeviceType named Test-DeviceType with Manufacturer named Test-Manufacturer"
        )
        self.assertEqual(test_device_type, None)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_validation_error(self, mock_logger, mock_device_type):
        """Test `create_device_type_object` Utility."""
        mock_device_type.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType", vendor_name="Test-Manufacturer", logger=logger
        )
        logger.error.assert_called_with(
            "Unable to create a new DeviceType named Test-DeviceType with Manufacturer named Test-Manufacturer"
        )
        self.assertEqual(test_device_type, None)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_tag_db_error(self, mock_logger, mock_tag_object):
        """Test `create_device_type_object` Utility."""
        mock_tag_object.side_effect = [None, DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType-new", vendor_name="Test-Manufacturer", logger=logger
        )
        self.assertEqual(test_device_type.model, "Test-DeviceType-new")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on DeviceType Test-DeviceType-new with an ID of {test_device_type.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_tag_validation_error(self, mock_logger, mock_tag_object):
        """Test `create_device_type_object` Utility."""
        mock_tag_object.side_effect = [None, ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_device_type = get_or_create_device_type_object(
            device_type="Test-DeviceType-new", vendor_name="Test-Manufacturer", logger=logger
        )
        self.assertEqual(test_device_type.model, "Test-DeviceType-new")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on DeviceType Test-DeviceType-new with an ID of {test_device_type.id}"
        )

    def test_get_or_create_manufacturer_object(self):
        """Test `get_or_create_manufacturer_object` Utility."""
        test_manufacturer = get_or_create_manufacturer_object(vendor_name="Test-Manufacturer")
        self.assertEqual(test_manufacturer.id, self.manufacturer.id)

    def test_get_or_create_platform_object_platform_created_no_napalm_driver(self):
        """Test `get_or_create_platform_object_object` Utility."""
        platform = "does_not_exist"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = get_or_create_platform_object(platform, self.manufacturer)
        self.assertEqual(self.manufacturer.id, platform_obj.manufacturer.id)
        self.assertEqual(platform_obj.name, platform)
        expected_network_driver = f"{self.manufacturer.name.lower()}_{platform}"
        self.assertEqual(platform_obj.network_driver, expected_network_driver)
        self.assertEqual(platform_obj.napalm_driver, "")

    def test_get_or_create_platform_object_platform_created_with_napalm_driver(self):
        """Test `get_or_create_platform_object` Utility."""
        manufacturer_obj, _ = Manufacturer.objects.get_or_create(name="Cisco")
        platform = "ios"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = get_or_create_platform_object(platform, manufacturer_obj)
        self.assertEqual(manufacturer_obj.id, platform_obj.manufacturer.id)
        self.assertEqual(platform_obj.name, platform)
        self.assertEqual(platform_obj.network_driver, "cisco_ios")
        self.assertEqual(platform_obj.napalm_driver, "cisco_ios")

    def test_get_or_create_platform_object_platform_created_iosxe(self):
        """Test `create_platform_object` Utility."""
        platform = "ios-xe"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = get_or_create_platform_object(platform, self.manufacturer)
        self.assertEqual(platform_obj.network_driver, "cisco_ios")
        self.assertEqual(platform_obj.napalm_driver, "cisco_ios")

    def test_get_or_create_platform_object_existing_platform_returned(self):
        """Test `get_or_create_platform_object` Utility."""
        manufacturer_obj, _ = Manufacturer.objects.get_or_create(name="Cisco")
        platform = "ios"
        platform_obj = Platform.objects.create(name=platform, manufacturer=manufacturer_obj)
        existing_platform_obj = get_or_create_platform_object(platform, manufacturer_obj)
        self.assertEqual(platform_obj.id, existing_platform_obj.id)
        self.assertEqual(platform_obj.network_driver, "")
        self.assertEqual(platform_obj.napalm_driver, "")

    def test_get_or_create_device_role(self):
        """Test `get_or_create_device_role` Utility."""
        test_device_role = get_or_create_device_role_object("Test-Role", role_color=ColorChoices.COLOR_RED)
        self.assertEqual(test_device_role.id, self.device_role.id)

    def test_get_or_create_status_object(self):
        """Test `get_or_create_status_object` Utility."""
        test_status = get_or_create_status_object(status_name="Test-Status", status_color=ColorChoices.COLOR_AMBER)
        self.assertEqual(test_status.id, self.status.id)

    def test_get_or_create_status_object_doesnt_exist(self):
        """Test `get_or_create_status_object` Utility."""
        test_status = get_or_create_status_object(status_name="Test-Status-100", status_color=ColorChoices.COLOR_AMBER)
        self.assertEqual(test_status.id, Status.objects.get(name="Test-Status-100").id)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    def test_create_ip(self, mock_ipaddress_to_interface):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.2", 32)
        self.assertEqual(test_ip.host, "192.168.0.2")
        self.assertEqual(test_ip.mask_length, 32)
        self.assertEqual(test_ip.status.name, "Active")
        self.assertEqual(test_ip.parent, self.prefix)
        mock_ipaddress_to_interface.assert_not_called()

    def test_create_ip_assign_interface(self):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.2", 32, object_pk=self.device.interfaces.first())
        self.assertEqual(test_ip.host, "192.168.0.2")
        self.assertEqual(test_ip.mask_length, 32)
        self.assertEqual(test_ip.parent, self.prefix)
        self.assertEqual(test_ip, self.device.interfaces.first().ip_addresses.get(host="192.168.0.2"))

    def test_create_ip_alread_exists(self):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.1", 32)
        self.assertEqual(test_ip.id, self.ip_address.id)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_fail_to_get_status_multiple_returned(self, mock_logger, mock_ipaddress, mock_status):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.side_effect = [Status.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", 32, logger=logger)
        mock_ipaddress.assert_not_called()
        logger.error.assert_called_with(
            "Multiple Statuses returned with name Active, and therefore cannot create an IPAddress of 192.168.0.1/32"
        )
        self.assertEqual(test_ip, None)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_fail_to_get_status_does_not_exist(self, mock_logger, mock_ipaddress, mock_status):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.side_effect = [Status.DoesNotExist]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", 32, logger=logger)
        mock_ipaddress.assert_not_called()
        logger.error.assert_called_with(
            "Unable to find a Status with the name Active, and therefore cannot create an IPAddress of 192.168.0.1/32"
        )
        self.assertEqual(test_ip, None)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_does_not_tag_the_interface(self, mock_logger, mock_restamp):
        """Only the IPAddress is stamped; stamping the Interface as well doubles what it costs."""
        logger = mock_logger("nb_job")
        interface_obj = self.device.interfaces.first()
        create_ip("192.168.0.1", 32, object_pk=interface_obj, logger=logger)
        stamped = [call.args[0] for call in mock_restamp.call_args_list]
        self.assertEqual(stamped, [self.ip_address])

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_ip_db_error(self, mock_logger, mock_restamp):
        """An address whose re-stamp fails is still returned, with a warning."""
        logger = mock_logger("nb_job")
        mock_restamp.side_effect = [DjangoBaseDBError]
        test_ip = create_ip("192.168.0.1", 32, logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on IPAddress {test_ip.address} with an ID of {test_ip.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_ip_validation_error(self, mock_logger, mock_restamp):
        """An address whose re-stamp fails is still returned, with a warning."""
        logger = mock_logger("nb_job")
        mock_restamp.side_effect = [ValidationError("failure")]
        test_ip = create_ip("192.168.0.1", 32, logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on IPAddress {test_ip.address} with an ID of {test_ip.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_refuses_an_address_with_no_subnet_mask(self, mock_logger, mock_ip_get_or_create):
        logger = mock_logger("nb_job")

        self.assertIsNone(create_ip("10.0.0.1", None, logger=logger))
        self.assertIsNone(create_ip("10.0.0.1", 0, logger=logger))

        mock_ip_get_or_create.assert_not_called()
        self.assertEqual(logger.warning.call_count, 2)
        self.assertIn("no subnet mask", logger.warning.call_args[0][0])

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create")
    def test_create_ip_refuses_an_address_with_no_subnet_mask_and_no_logger(self, mock_ip_get_or_create):
        self.assertIsNone(create_ip("10.0.0.1", None))

        mock_ip_get_or_create.assert_not_called()

    def test_create_vlan_updates_location_content_types(self):
        """Test `create_vlan` ensures location type allows VLAN content type."""
        # Create a location type that doesn't allow VLANs initially
        loc_type = LocationType.objects.create(name="NoVLANs")
        location = Location.objects.create(
            name="Test-NoVLAN-Location",
            location_type=loc_type,
            status=Status.objects.get(name="Active"),
        )

        # Verify initial state
        vlan_ct = ContentType.objects.get_for_model(VLAN)
        self.assertNotIn(vlan_ct, loc_type.content_types.all())

        # Create VLAN
        vlan = create_vlan(
            vlan_name="Test-VLAN",
            vlan_id=100,
            vlan_status="Active",
            location_obj=location,
            description="Test Description",
        )

        # Verify VLAN was created and associated with location
        self.assertIsNotNone(vlan)
        self.assertEqual(vlan.location, location)

        # Verify location type now allows VLANs
        self.assertIn(vlan_ct, loc_type.content_types.all())

    def test_create_interface(self):
        """Test `create_interface` Utility."""
        interface_details = {"name": "Test-Interface", "type": "virtual"}
        test_interface = create_interface(self.device, interface_details)
        self.assertEqual(test_interface.id, self.device.interfaces.get(name="Test-Interface").id)

    def test_create_interface_new(self):
        """Test `create_interface` Utility for new interface."""
        interface_details = {"name": "Test-Interface-New", "type": "virtual", "mtu": 1500}
        test_interface = create_interface(self.device, interface_details)
        self.assertEqual(test_interface.id, self.device.interfaces.get(name="Test-Interface-New").id)
        self.assertEqual(test_interface.mtu, 1500)

    # ===== get_or_create_manufacturer_object error/tag paths =====

    def test_get_or_create_manufacturer_object_new(self):
        """Test creating a new Manufacturer."""
        self.assertFalse(Manufacturer.objects.filter(name="New-Manufacturer").exists())
        result = get_or_create_manufacturer_object(vendor_name="New-Manufacturer")
        self.assertEqual(result.name, "New-Manufacturer")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Manufacturer.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_manufacturer_object_multiple_returned(self, mock_logger, mock_mfg):
        """Test `get_or_create_manufacturer_object` MultipleObjectsReturned path."""
        mock_mfg.side_effect = [Manufacturer.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = get_or_create_manufacturer_object(vendor_name="X-Mfg", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple Manufacturers returned with name X-Mfg")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Manufacturer.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_manufacturer_object_db_error(self, mock_logger, mock_mfg):
        """Test `get_or_create_manufacturer_object` DjangoBaseDBError path."""
        mock_mfg.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_manufacturer_object(vendor_name="X-Mfg", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Manufacturer named X-Mfg")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Manufacturer.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_manufacturer_object_validation_error(self, mock_logger, mock_mfg):
        """Test `get_or_create_manufacturer_object` ValidationError path."""
        mock_mfg.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_manufacturer_object(vendor_name="X-Mfg", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Manufacturer named X-Mfg")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_manufacturer_object_tag_db_error(self, mock_logger, mock_tag):
        """Test `get_or_create_manufacturer_object` tag_object DjangoBaseDBError path."""
        mock_tag.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_manufacturer_object(vendor_name="Tag-DB-Mfg", logger=logger)
        self.assertEqual(result.name, "Tag-DB-Mfg")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on Manufacturer Tag-DB-Mfg with an ID of {result.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_manufacturer_object_tag_validation_error(self, mock_logger, mock_tag):
        """Test `get_or_create_manufacturer_object` tag_object ValidationError path."""
        mock_tag.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_manufacturer_object(vendor_name="Tag-V-Mfg", logger=logger)
        self.assertEqual(result.name, "Tag-V-Mfg")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on Manufacturer Tag-V-Mfg with an ID of {result.id}"
        )

    # ===== get_or_create_device_role_object error/tag paths =====

    def test_get_or_create_device_role_object_new(self):
        """Test creating a new Role with cf and content_type."""
        self.assertFalse(Role.objects.filter(name="New-Role").exists())
        result = get_or_create_device_role_object(role_name="New-Role", role_color=ColorChoices.COLOR_BLUE)
        self.assertEqual(result.name, "New-Role")
        self.assertEqual(result.cf.get("ipfabric_type"), "New-Role")
        self.assertIn(self.content_type, result.content_types.all())

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Role.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_device_role_object_db_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_device_role_object` DjangoBaseDBError on create path."""
        mock_create.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_device_role_object(role_name="DB-Role", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Role named DB-Role")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Role.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_device_role_object_validation_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_device_role_object` ValidationError on create path."""
        mock_create.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_device_role_object(role_name="V-Role", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Role named V-Role")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Role.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_device_role_object_multiple_returned(self, mock_logger, mock_get):
        """Test `get_or_create_device_role_object` MultipleObjectsReturned path."""
        mock_get.side_effect = [Role.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = get_or_create_device_role_object(role_name="Multi-Role", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple Roles returned with the name Multi-Role")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_device_role_object_tag_db_error(self, mock_logger, mock_tag):
        """Test `get_or_create_device_role_object` tag_object DjangoBaseDBError path."""
        mock_tag.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_device_role_object(role_name="TagDB-Role", logger=logger)
        self.assertEqual(result.name, "TagDB-Role")
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on Role TagDB-Role with an ID of {result.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_device_role_object_tag_validation_error(self, mock_logger, mock_tag):
        """Test `get_or_create_device_role_object` tag_object ValidationError path."""
        mock_tag.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_device_role_object(role_name="TagV-Role", logger=logger)
        self.assertEqual(result.name, "TagV-Role")
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on Role TagV-Role with an ID of {result.id}"
        )

    # ===== get_or_create_status_object error paths =====

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_status_object_db_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_status_object` DjangoBaseDBError on create path."""
        mock_create.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_status_object(
            status_name="DB-Status", status_color=ColorChoices.COLOR_AMBER, logger=logger
        )
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Status named DB-Status")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_status_object_validation_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_status_object` ValidationError on create path."""
        mock_create.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_status_object(
            status_name="V-Status", status_color=ColorChoices.COLOR_AMBER, logger=logger
        )
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Status named V-Status")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_status_object_multiple_returned(self, mock_logger, mock_get):
        """Test `get_or_create_status_object` MultipleObjectsReturned path."""
        mock_get.side_effect = [Status.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = get_or_create_status_object(
            status_name="Multi-Status", status_color=ColorChoices.COLOR_AMBER, logger=logger
        )
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple Statuses returned with the name Multi-Status")

    # ===== get_or_create_platform_object error paths =====

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_no_manufacturer(self, mock_logger):
        """Test `get_or_create_platform_object` returns None when manufacturer is None."""
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(platform="ios", manufacturer_obj=None, logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create Platform ios because Manufacturer is None")

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_manufacturer_mismatch(self, mock_logger):
        """Test `get_or_create_platform_object` returns None when Platform belongs to a different Manufacturer."""
        other_mfg = Manufacturer.objects.create(name="Other-Mfg")
        Platform.objects.create(name="shared-platform", manufacturer=self.manufacturer)
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(platform="shared-platform", manufacturer_obj=other_mfg, logger=logger)
        self.assertIsNone(result)
        logger.warning.assert_called_with(
            f"Platform shared-platform already exists but belongs to Manufacturer {self.manufacturer}, "
            f"not {other_mfg}. Skipping assignment to avoid validation errors."
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Platform.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_db_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_platform_object` DjangoBaseDBError on create path."""
        mock_create.side_effect = [DjangoBaseDBError("err")]
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(platform="db-fail", manufacturer_obj=self.manufacturer, logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)
        self.assertIn("Unable to create a new Platform named db-fail", logger.error.call_args[0][0])

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Platform.objects.create", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_validation_error_on_create(self, mock_logger, mock_create):
        """Test `get_or_create_platform_object` ValidationError on create path."""
        mock_create.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(platform="v-fail", manufacturer_obj=self.manufacturer, logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Platform.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_multiple_returned(self, mock_logger, mock_get):
        """Test `get_or_create_platform_object` MultipleObjectsReturned path."""
        mock_get.side_effect = [Platform.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(platform="multi", manufacturer_obj=self.manufacturer, logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple Platforms returned with the name multi")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Platform.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_platform_object_db_error_on_get(self, mock_logger, mock_get):
        """Test `get_or_create_platform_object` DjangoBaseDBError on get path."""
        mock_get.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_platform_object(
            platform="get-db-fail", manufacturer_obj=self.manufacturer, logger=logger
        )
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to retrieve Platform named get-db-fail")

    # ===== get_or_create_tag_object =====

    def test_get_or_create_tag_object_existing(self):
        """Test `get_or_create_tag_object` returns existing Tag."""
        existing, _ = Tag.objects.get_or_create(name="Existing-Tag", defaults={"color": ColorChoices.COLOR_GREY})
        result = get_or_create_tag_object(tag_name="Existing-Tag")
        self.assertEqual(result.id, existing.id)

    def test_get_or_create_tag_object_new(self):
        """Test `get_or_create_tag_object` creates new Tag and adds default content_type."""
        self.assertFalse(Tag.objects.filter(name="New-Tag").exists())
        result = get_or_create_tag_object(tag_name="New-Tag", tag_color=ColorChoices.COLOR_BLUE)
        self.assertEqual(result.name, "New-Tag")
        self.assertIn(self.content_type, result.content_types.all())

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Tag.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_tag_object_db_error(self, mock_logger, mock_tag):
        """Test `get_or_create_tag_object` DjangoBaseDBError path."""
        mock_tag.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = get_or_create_tag_object(tag_name="DB-Tag", logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Tag.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_tag_object_validation_error(self, mock_logger, mock_tag):
        """Test `get_or_create_tag_object` ValidationError path."""
        mock_tag.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_tag_object(tag_name="V-Tag", logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Tag.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_tag_object_multiple_returned(self, mock_logger, mock_tag):
        """Test `get_or_create_tag_object` MultipleObjectsReturned path (nbutils.py lines 373-376)."""
        mock_tag.side_effect = [Tag.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = get_or_create_tag_object(tag_name="Multi-Tag", logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple Tags returned with the name Multi-Tag")

    # ===== get_or_create_virtual_chassis_object =====

    def test_get_or_create_virtual_chassis_object_existing(self):
        """Test `get_or_create_virtual_chassis_object` returns existing VC."""
        existing = VirtualChassis.objects.create(name="Stack-1")
        result = get_or_create_virtual_chassis_object(name="Stack-1")
        self.assertEqual(result.id, existing.id)

    def test_get_or_create_virtual_chassis_object_new(self):
        """Test `get_or_create_virtual_chassis_object` creates new VC."""
        self.assertFalse(VirtualChassis.objects.filter(name="Stack-New").exists())
        result = get_or_create_virtual_chassis_object(name="Stack-New")
        self.assertEqual(result.name, "Stack-New")
        self.assertTrue(VirtualChassis.objects.filter(name="Stack-New").exists())

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.VirtualChassis.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_virtual_chassis_object_db_error(self, mock_logger, mock_vc):
        """Test `get_or_create_virtual_chassis_object` DjangoBaseDBError path."""
        mock_vc.side_effect = [DjangoBaseDBError("err-msg")]
        logger = mock_logger("nb_job")
        result = get_or_create_virtual_chassis_object(name="Stack-Err", logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)
        self.assertIn(
            "Unable to get or create VirtualChassis named Stack-Err",
            logger.error.call_args[0][0],
        )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.VirtualChassis.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_virtual_chassis_object_validation_error(self, mock_logger, mock_vc):
        """Test `get_or_create_virtual_chassis_object` ValidationError path."""
        mock_vc.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = get_or_create_virtual_chassis_object(name="Stack-VErr", logger=logger)
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    # ===== assign_device_to_virtual_chassis =====

    def _make_vc_test_device(self, name):
        """Create a fresh device for VirtualChassis tests."""
        return Device.objects.create(
            name=name,
            location=self.location,
            device_type=self.device_type,
            role=self.device_role,
            status=Status.objects.get(name="Active"),
        )

    def test_assign_device_to_virtual_chassis_initial(self):
        """Test initial assignment with VC, position, and priority."""
        vc = VirtualChassis.objects.create(name="Stack-Init")
        device = self._make_vc_test_device("VC-Initial")
        result = assign_device_to_virtual_chassis(device, vc, position=1, priority=10)
        device.refresh_from_db()
        self.assertEqual(result.id, vc.id)
        self.assertEqual(device.virtual_chassis_id, vc.id)
        self.assertEqual(device.vc_position, 1)
        self.assertEqual(device.vc_priority, 10)

    def test_assign_device_to_virtual_chassis_idempotent(self):
        """Test that calling twice with same args is a no-op on the second call."""
        vc = VirtualChassis.objects.create(name="Stack-Idem")
        device = self._make_vc_test_device("VC-Idem")
        assign_device_to_virtual_chassis(device, vc, position=1, priority=10)
        device.refresh_from_db()
        with mock.patch.object(Device, "validated_save") as save_mock:
            assign_device_to_virtual_chassis(device, vc, position=1, priority=10)
            save_mock.assert_not_called()

    def test_assign_device_to_virtual_chassis_position_only(self):
        """Test setting position without priority."""
        vc = VirtualChassis.objects.create(name="Stack-Pos")
        device = self._make_vc_test_device("VC-Pos")
        assign_device_to_virtual_chassis(device, vc, position=2)
        device.refresh_from_db()
        self.assertEqual(device.vc_position, 2)
        self.assertIsNone(device.vc_priority)

    def test_assign_device_to_virtual_chassis_master_set(self):
        """Test setting master saves VC with the new master."""
        vc = VirtualChassis.objects.create(name="Stack-Master")
        device = self._make_vc_test_device("VC-Master")
        assign_device_to_virtual_chassis(device, vc, position=1, master=True)
        vc.refresh_from_db()
        self.assertEqual(vc.master_id, device.id)

    def test_assign_device_to_virtual_chassis_master_idempotent(self):
        """Test that re-assigning the same master is a no-op on the VC save."""
        vc = VirtualChassis.objects.create(name="Stack-MasterIdem")
        device = self._make_vc_test_device("VC-MasterIdem")
        assign_device_to_virtual_chassis(device, vc, position=1, master=True)
        with mock.patch.object(VirtualChassis, "validated_save") as save_mock:
            assign_device_to_virtual_chassis(device, vc, position=1, master=True)
            save_mock.assert_not_called()

    def test_assign_device_to_virtual_chassis_priority_update(self):
        """Calling again with a new priority updates priority and persists."""
        vc = VirtualChassis.objects.create(name="Stack-PriUpdate")
        device = self._make_vc_test_device("VC-PriUpdate")
        assign_device_to_virtual_chassis(device, vc, position=1, priority=10)
        device.refresh_from_db()
        self.assertEqual(device.vc_priority, 10)

        assign_device_to_virtual_chassis(device, vc, position=1, priority=20)
        device.refresh_from_db()
        self.assertEqual(device.vc_priority, 20)

    def test_assign_device_to_virtual_chassis_position_change(self):
        """Calling again with a different position updates position and persists."""
        vc = VirtualChassis.objects.create(name="Stack-PosChange")
        device = self._make_vc_test_device("VC-PosChange")
        assign_device_to_virtual_chassis(device, vc, position=1)
        device.refresh_from_db()
        self.assertEqual(device.vc_position, 1)

        assign_device_to_virtual_chassis(device, vc, position=3)
        device.refresh_from_db()
        self.assertEqual(device.vc_position, 3)

    def test_assign_device_to_virtual_chassis_master_swap(self):
        """Setting master=True for a different device flips the VC master."""
        vc = VirtualChassis.objects.create(name="Stack-MasterSwap")
        first = self._make_vc_test_device("VC-MasterSwap-1")
        second = self._make_vc_test_device("VC-MasterSwap-2")
        assign_device_to_virtual_chassis(first, vc, position=1, master=True)
        vc.refresh_from_db()
        self.assertEqual(vc.master_id, first.id)

        assign_device_to_virtual_chassis(second, vc, position=2, master=True)
        vc.refresh_from_db()
        self.assertEqual(vc.master_id, second.id)

    # ===== get_syncable_device =====

    def test_get_syncable_device_match(self):
        """Test returns the device when name and SSoT tag match."""
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric", defaults={"color": ColorChoices.COLOR_LIGHT_GREEN}
        )
        ssot_tag.content_types.add(self.content_type)
        self.device.tags.add(ssot_tag)
        result = get_syncable_device(self.device.name, tagged_only=True)
        self.assertEqual(result.id, self.device.id)

    def test_get_syncable_device_no_match(self):
        """Test returns None when device has no SSoT tag."""
        result = get_syncable_device("Test-Device", tagged_only=True)
        self.assertIsNone(result)

    def test_get_syncable_device_finds_an_untagged_device_when_the_run_is_not_tagged_only(self):
        """The Nautobot adapter loads every Device then, so every Device has to be writable."""
        result = get_syncable_device(self.device.name, tagged_only=False)
        self.assertEqual(result.id, self.device.id)

    def test_get_syncable_device_cache_reuse(self):
        """Test second call hits the cache and skips DB."""
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric", defaults={"color": ColorChoices.COLOR_LIGHT_GREEN}
        )
        ssot_tag.content_types.add(self.content_type)
        self.device.tags.add(ssot_tag)
        first = get_syncable_device(self.device.name, tagged_only=True)
        with mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Device.objects.filter") as mock_filter:
            second = get_syncable_device(self.device.name, tagged_only=True)
            mock_filter.assert_not_called()
        self.assertIs(first, second)

    # ===== get_tagged_interface =====

    def _tag_test_device(self):
        """Tag `self.device` as synced from IPFabric so it is visible to the tagged lookups."""
        ssot_tag, _ = Tag.objects.get_or_create(
            name="SSoT Synced from IPFabric", defaults={"color": ColorChoices.COLOR_LIGHT_GREEN}
        )
        ssot_tag.content_types.add(self.content_type)
        self.device.tags.add(ssot_tag)

    def test_get_tagged_interface_match(self):
        """Test returns the Interface when the Device is tagged and the Interface exists."""
        self._tag_test_device()
        interface = self.device.interfaces.get(name="Test-Interface")

        result = get_tagged_interface(self.device.name, "Test-Interface", tagged_only=True)

        self.assertEqual(result.id, interface.id)

    def test_get_tagged_interface_device_not_tagged(self):
        """Test returns None and warns when the Device is not tagged as synced."""
        mock_logger = mock.MagicMock()

        result = get_tagged_interface(self.device.name, "Test-Interface", tagged_only=True, logger=mock_logger)

        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()

    def test_get_tagged_interface_does_not_exist(self):
        """Test returns None and warns when the Interface is absent from a tagged Device."""
        self._tag_test_device()
        mock_logger = mock.MagicMock()

        result = get_tagged_interface(self.device.name, "Ethernet9/9", tagged_only=True, logger=mock_logger)

        self.assertIsNone(result)
        mock_logger.warning.assert_called_once()

    def test_get_tagged_interface_multiple_returned(self):
        """Test returns None and errors when the Interface name is ambiguous."""
        self._tag_test_device()
        mock_logger = mock.MagicMock()

        with mock.patch.object(Device, "interfaces", new_callable=mock.PropertyMock) as mock_interfaces:
            mock_interfaces.return_value.get.side_effect = Interface.MultipleObjectsReturned
            result = get_tagged_interface(self.device.name, "Test-Interface", tagged_only=True, logger=mock_logger)

        self.assertIsNone(result)
        mock_logger.error.assert_called_once()

    def test_get_tagged_interface_no_logger(self):
        """Test the logger is optional on every failure path."""
        self.assertIsNone(get_tagged_interface(self.device.name, "Test-Interface", tagged_only=True))
        self._tag_test_device()
        self.assertIsNone(get_tagged_interface(self.device.name, "Ethernet9/9", tagged_only=True))

    # ===== tag_object (direct) =====

    def test_tag_object_adds_tag_and_cf(self):
        """Test `tag_object` adds tag and writes cf values."""
        tag_object(nautobot_object=self.device, custom_field=LAST_SYNCHRONIZED_CF_NAME)
        self.device.refresh_from_db()
        self.assertEqual(self.device.cf.get("system_of_record"), "IPFabric")
        self.assertIn("SSoT Synced from IPFabric", [t.name for t in self.device.tags.all()])

    def test_tag_object_alternate_tag_name(self):
        """Test `tag_object` with an alternate tag_name."""
        Tag.objects.get_or_create(name="Custom-Tag", defaults={"color": ColorChoices.COLOR_GREY})
        tag_object(
            nautobot_object=self.device,
            custom_field=LAST_SYNCHRONIZED_CF_NAME,
            tag_name="Custom-Tag",
        )
        self.device.refresh_from_db()
        self.assertIn("Custom-Tag", [t.name for t in self.device.tags.all()])

    # ===== create_vlan error/tag paths =====

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.VLAN.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_vlan_multiple_returned(self, mock_logger, mock_vlan):
        """Test `create_vlan` MultipleObjectsReturned path."""
        mock_vlan.side_effect = [VLAN.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        result = create_vlan(
            vlan_name="Multi-VLAN",
            vlan_id=200,
            vlan_status="Active",
            location_obj=self.location,
            description="t",
            logger=logger,
        )
        self.assertIsNone(result)
        logger.error.assert_called_with("Multiple VLANs returned with name Multi-VLAN and ID 200")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.VLAN.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_vlan_db_error(self, mock_logger, mock_vlan):
        """Test `create_vlan` DjangoBaseDBError path."""
        mock_vlan.side_effect = [DjangoBaseDBError("oops")]
        logger = mock_logger("nb_job")
        result = create_vlan(
            vlan_name="DB-VLAN",
            vlan_id=201,
            vlan_status="Active",
            location_obj=self.location,
            description="t",
            logger=logger,
        )
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.VLAN.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_vlan_validation_error(self, mock_logger, mock_vlan):
        """Test `create_vlan` ValidationError path."""
        mock_vlan.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = create_vlan(
            vlan_name="V-VLAN",
            vlan_id=202,
            vlan_status="Active",
            location_obj=self.location,
            description="t",
            logger=logger,
        )
        self.assertIsNone(result)
        self.assertTrue(logger.error.called)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_vlan_tag_db_error(self, mock_logger, mock_tag):
        """Test `create_vlan` tag_object DjangoBaseDBError path."""
        mock_tag.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        result = create_vlan(
            vlan_name="TagDB-VLAN",
            vlan_id=203,
            vlan_status="Active",
            location_obj=self.location,
            description="t",
            logger=logger,
        )
        self.assertEqual(result.name, "TagDB-VLAN")
        self.assertTrue(logger.warning.called)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_vlan_tag_validation_error(self, mock_logger, mock_tag):
        """Test `create_vlan` tag_object ValidationError path."""
        mock_tag.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        result = create_vlan(
            vlan_name="TagV-VLAN",
            vlan_id=204,
            vlan_status="Active",
            location_obj=self.location,
            description="t",
            logger=logger,
        )
        self.assertEqual(result.name, "TagV-VLAN")
        self.assertTrue(logger.warning.called)

    # ===== create_interface error/tag paths =====

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_interface_db_error(self, mock_logger):
        """Test `create_interface` DjangoBaseDBError on get_or_create path."""
        logger = mock_logger("nb_job")
        mock_device = mock.MagicMock()
        mock_device.name = "Mock-Device"
        mock_device.interfaces.filter.side_effect = DjangoBaseDBError
        result = create_interface(mock_device, {"name": "DB-Iface"}, logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Interface named DB-Iface on Device named Mock-Device")

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_interface_validation_error(self, mock_logger):
        """Test `create_interface` ValidationError on get_or_create path."""
        logger = mock_logger("nb_job")
        mock_device = mock.MagicMock()
        mock_device.name = "Mock-Device"
        mock_device.interfaces.filter.side_effect = ValidationError("failure")
        result = create_interface(mock_device, {"name": "V-Iface"}, logger=logger)
        self.assertIsNone(result)
        logger.error.assert_called_with("Unable to create a new Interface named V-Iface on Device named Mock-Device")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.get_or_create_status_object",
        return_value=None,
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_interface_status_helper_returns_none(self, mock_logger, _mock_status_helper):
        """Test `create_interface` returns None and logs when status helper returns None (nbutils.py line 545)."""
        logger = mock_logger("nb_job")
        mock_device = mock.MagicMock()
        mock_device.name = "Mock-Device"
        result = create_interface(mock_device, {"name": "NoStat-Iface"}, logger=logger)
        self.assertIsNone(result)
        mock_device.interfaces.filter.assert_not_called()
        logger.error.assert_called_with(
            "Unable to set Status of Active for Interface named NoStat-Iface on Device named Mock-Device"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_interface_tag_db_error(self, mock_logger, mock_tag):
        """An existing Interface whose re-tagging fails is still returned, with a warning."""
        mock_tag.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        Interface.objects.create(
            device=self.device, name="TagDB-Iface", status=Status.objects.get(name="Active"), type="virtual"
        )
        result = create_interface(self.device, {"name": "TagDB-Iface", "type": "virtual"}, logger=logger)
        self.assertEqual(result.name, "TagDB-Iface")
        self.assertTrue(logger.warning.called)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.restamp_synced")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_interface_tag_validation_error(self, mock_logger, mock_tag):
        """An existing Interface whose re-tagging fails validation is still returned, with a warning."""
        mock_tag.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        Interface.objects.create(
            device=self.device, name="TagV-Iface", status=Status.objects.get(name="Active"), type="virtual"
        )
        result = create_interface(self.device, {"name": "TagV-Iface", "type": "virtual"}, logger=logger)
        self.assertEqual(result.name, "TagV-Iface")
        self.assertTrue(logger.warning.called)

    # ===== lookup-only helper ambiguity paths =====

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Manufacturer.objects.get", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_manufacturer_object_multiple_returned(self, mock_logger, mock_get):
        """An ambiguous name is reported rather than resolved arbitrarily."""
        mock_get.side_effect = [Manufacturer.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_manufacturer_object("X-Mfg", logger=logger))
        logger.error.assert_called_with("Multiple Manufacturers returned with name X-Mfg")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_device_type_object_multiple_returned(self, mock_logger, mock_get):
        """Two DeviceTypes sharing a model cannot be told apart on the model alone."""
        mock_get.side_effect = [DeviceType.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_device_type_object("X-Model", logger=logger))
        logger.error.assert_called_with("Multiple DeviceTypes returned with model X-Model")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Role.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_device_role_object_multiple_returned(self, mock_logger, mock_get):
        """An ambiguous Role stops the lookup rather than falling through to the name match."""
        mock_get.side_effect = [Role.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_device_role_object("X-Role", logger=logger))
        logger.error.assert_called_with("Multiple Roles returned with the name X-Role")

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Platform.objects.get", autospec=True)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_platform_object_multiple_returned(self, mock_logger, mock_get):
        """Two Platforms sharing a name cannot be told apart without a Manufacturer."""
        mock_get.side_effect = [Platform.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        self.assertIsNone(get_platform_object("X-Platform", logger=logger))
        logger.error.assert_called_with("Multiple Platforms returned with name X-Platform")

    def test_get_device_role_object_falls_back_to_the_name(self):
        """A Role from a system that does not set the IP Fabric custom field is still found."""
        role = Role.objects.create(name="Externally-Owned-Role")
        self.assertEqual(get_device_role_object("Externally-Owned-Role"), role)

    def test_get_device_role_object_returns_none_when_absent(self):
        """A Role neither matched on the custom field nor on the name is reported missing."""
        self.assertIsNone(get_device_role_object("No-Such-Role"))

    # ===== failure paths a bad estate reaches, and the reuse paths a second run reaches =====

    @mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.CustomField.objects.get_or_create")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_a_location_id_is_not_recorded_when_its_custom_field_is_ambiguous(self, mock_logger, mock_get_or_create):
        """The Location still loads; only the IP Fabric site id it could not file is lost."""
        logger = mock_logger("nb_job")
        mock_get_or_create.side_effect = CustomField.MultipleObjectsReturned

        location = get_or_create_location_object(location_name="Test-Location", location_id="site-1", logger=logger)

        self.assertEqual(location.id, self.location.id)
        self.assertFalse(location.cf.get("ipfabric_site_id"))
        logger.error.assert_called_with("Multiple CustomFields returned with key ipfabric_site_id")

    @mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.CustomField.objects.get_or_create")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_a_location_id_is_not_recorded_when_its_custom_field_cannot_be_created(
        self, mock_logger, mock_get_or_create
    ):
        logger = mock_logger("nb_job")
        mock_get_or_create.side_effect = ValidationError("refused")

        location = get_or_create_location_object(location_name="Test-Location", location_id="site-1", logger=logger)

        self.assertEqual(location.id, self.location.id)
        self.assertFalse(location.cf.get("ipfabric_site_id"))
        logger.error.assert_called_with(
            "Unable to create a new CustomField named ipfabric_site_id with type of TYPE_TEXT"
        )

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_reports_a_new_address_the_database_refuses(self, mock_logger):
        """A refused address returns None rather than a half-written one the caller would assign."""
        logger = mock_logger("nb_job")

        with mock.patch.object(IPAddress, "validated_save", side_effect=ValidationError("refused")):
            result = create_ip("192.168.1.5", 24, logger=logger)

        self.assertIsNone(result)
        self.assertFalse(IPAddress.objects.filter(host="192.168.1.5").exists())
        self.assertIn("Unable to create a new IPAddress", logger.error.call_args[0][0])

    @mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_reports_a_mask_it_could_not_change(self, mock_logger, mock_tag_object):
        """Reported as an error, not the warning an unchanged mask gets: the mask is what the sync keeps."""
        logger = mock_logger("nb_job")
        mock_tag_object.side_effect = ValidationError("refused")

        result = create_ip("192.168.0.1", 16, logger=logger)

        self.assertEqual(result.id, self.ip_address.id)
        self.assertEqual(result.mask_length, 32, "The refused mask must not be left set in memory.")
        self.assertIn("Unable to change the mask", logger.error.call_args[0][0])
        logger.warning.assert_not_called()

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_reports_an_interface_assignment_the_database_refuses(self, mock_logger):
        """The address itself is still returned, since only the assignment row failed."""
        logger = mock_logger("nb_job")
        interface = self.device.interfaces.first()

        with mock.patch.object(IPAddressToInterface, "validated_save", side_effect=ValidationError("refused")):
            result = create_ip("192.168.0.1", 32, object_pk=interface, logger=logger)

        self.assertEqual(result.id, self.ip_address.id)
        self.assertFalse(interface.ip_addresses.filter(pk=self.ip_address.pk).exists())
        self.assertIn("Unable to assign IPAddress", logger.error.call_args[0][0])

    @mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.resolve_ip", return_value=None)
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_queue_ip_reports_an_address_it_could_not_resolve(self, mock_logger, _mock_resolve_ip):
        """Nothing is queued, so the batch cannot carry a row the address was never built for."""
        logger = mock_logger("nb_job")
        pending = PendingWrites()

        result = queue_ip(
            address="192.168.9.9/24",
            status_obj=Status.objects.get(name="Active"),
            interface=None,
            pending=pending,
            logger=logger,
        )

        self.assertIsNone(result)
        self.assertEqual(len(pending), 0)
        self.assertIn("Unable to queue an IPAddress", logger.error.call_args[0][0])

    def test_create_parent_prefix_keeps_the_prefix_that_already_contains_the_address(self):
        """Checked for rather than inferred from a failure, so no second, wider Prefix is added."""
        before = Prefix.objects.count()

        self.assertTrue(create_parent_prefix("192.168.5.5/24"))

        self.assertEqual(Prefix.objects.count(), before)

    def test_create_ip_writes_an_ipv6_address(self):
        """The point of syncing IPv6: the whole write path has to carry a v6 address to the database.

        A netmask cannot describe one, so this exercises the length the sync records instead, and
        the parent Prefix created for an address whose subnet Nautobot does not hold.
        """
        interface = self.device.interfaces.first()

        address = create_ip("2001:db8:f00d::5", 64, object_pk=interface)

        self.assertIsNotNone(address, "The address was refused.")
        self.assertEqual(address.host, "2001:db8:f00d::5")
        self.assertEqual(address.mask_length, 64)
        self.assertEqual(str(address.parent.prefix), "2001:db8:f00d::/64")
        self.assertIn(address, interface.ip_addresses.all())

    def test_create_parent_prefix_keeps_an_ipv6_prefix_that_already_contains_the_address(self):
        """The covering route is `/128` for IPv6, not `/32`.

        A `/32` names a subnet millions of addresses wide, so no Prefix holding the address contains
        it and the check reports none where one exists. The redundant wider Prefix that follows can
        never become the parent, since Nautobot parents an address to the most specific Prefix
        containing it.
        """
        Prefix.objects.get_or_create(
            prefix="2001:db8:cafe::/64",
            namespace=get_default_namespace(),
            status=Status.objects.get(name="Active"),
        )
        before = Prefix.objects.count()

        self.assertTrue(create_parent_prefix("2001:db8:cafe::1/48"))

        self.assertEqual(Prefix.objects.count(), before, "A wider Prefix was created for an address already covered.")

    def test_create_vlan_reuses_a_vlan_the_location_already_has(self):
        """Matched on VLAN ID and Location, so the name IP Fabric reports does not overwrite it."""
        existing = VLAN.objects.create(vid=250, name="Pre-Existing", status=self.vlan_status)
        existing.locations.add(self.location)

        vlan = create_vlan(
            vlan_name="Reported-Name",
            vlan_id=250,
            vlan_status="Test-Vlan-Status",
            location_obj=self.location,
            description="",
        )

        self.assertEqual(vlan.pk, existing.pk)
        self.assertEqual(vlan.name, "Pre-Existing")
        self.assertEqual(VLAN.objects.filter(vid=250).count(), 1)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.VirtualChassis.objects.get")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_virtual_chassis_object_reports_an_ambiguous_name(self, mock_logger, mock_get):
        """Two stacks of one name cannot be told apart, so membership is left unrecorded."""
        logger = mock_logger("nb_job")
        mock_get.side_effect = VirtualChassis.MultipleObjectsReturned

        self.assertIsNone(get_virtual_chassis_object("stack1", logger=logger))

        logger.error.assert_called_with("Multiple VirtualChassis returned with the name stack1")

    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_get_or_create_status_object_matches_without_creating_when_told_not_to(self, mock_logger):
        """The one place the choice is made, so a caller with no access to the settings can be handed it."""
        logger = mock_logger("nb_job")

        self.assertIsNone(get_or_create_status_object("No-Such-Status", create=False, logger=logger))

        self.assertFalse(Status.objects.filter(name="No-Such-Status").exists())
        logger.debug.assert_called_with("No Status named %s exists yet", "No-Such-Status")

    def test_get_or_create_status_object_caches_matching_apart_from_creating(self):
        """`create` is part of the cache key, so a matching run must not answer a creating one."""
        self.assertIsNone(get_or_create_status_object("Cache-Split-Status", create=False))

        created = get_or_create_status_object("Cache-Split-Status", create=True)

        self.assertIsNotNone(created, "The creating call read the matching call's cached None.")
        self.assertEqual(created.name, "Cache-Split-Status")


class TestDeferredChangeLogging(TestCase):
    """Test the per-object change log deferral helper."""

    def setUp(self):
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        populate_status_choices()
        self.user = get_user_model().objects.create_user(username="deferral-tester")
        self.status = Status.objects.get(name="Active")

    def test_does_nothing_without_change_logging(self):
        """Adapters are driven directly as well as by jobs, and Nautobot raises if nothing is set up."""
        reached = False
        with deferred_change_logging():
            reached = True
        self.assertTrue(reached)

    def test_defers_while_inside_the_scope(self):
        context = JobChangeContext(user=self.user)
        with change_logging(context):
            self.assertFalse(context.defer_object_changes)
            with deferred_change_logging():
                self.assertTrue(context.defer_object_changes)
            self.assertFalse(context.defer_object_changes)

    def test_a_nested_scope_leaves_the_enclosing_one_deferring(self):
        """Exiting a nested scope would otherwise flush and discard what the outer one had pending."""
        context = JobChangeContext(user=self.user)
        with change_logging(context):
            with deferred_change_logging():
                self.status.description = "changed inside the outer scope"
                self.status.validated_save()
                self.assertEqual(len(context.deferred_object_changes), 1)
                with deferred_change_logging():
                    pass
                self.assertEqual(
                    len(context.deferred_object_changes),
                    1,
                    "The nested scope flushed the enclosing scope's pending changes.",
                )

    def test_it_works_as_a_decorator(self):
        """The model operations apply it as a decorator, and each call must re-enter the scope."""
        context = JobChangeContext(user=self.user)
        seen = []

        @deferred_change_logging()
        def operation():
            seen.append(context.defer_object_changes)
            return "returned"

        with change_logging(context):
            self.assertEqual(operation(), "returned")
            self.assertEqual(operation(), "returned")
        self.assertEqual(seen, [True, True], "The scope was not re-entered on the second call.")
