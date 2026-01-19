"""Test Nautobot Utilities."""

import unittest

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import Error as DjangoBaseDBError
from django.test import TestCase
from nautobot.core.choices import ColorChoices
from nautobot.dcim.models import DeviceType, Location, LocationType, Manufacturer, Platform
from nautobot.dcim.models.devices import Device
from nautobot.extras.models import Role
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import VLAN, IPAddress, Prefix, get_default_namespace

from nautobot_ssot.integrations.ipfabric.utilities import (
    create_device_type_object,
    create_interface,
    create_ip,
    create_location,
    create_manufacturer,
    create_platform_object,
    create_status,
    create_vlan,
    get_or_create_device_role_object,
)


# pylint: disable=too-many-instance-attributes,too-many-arguments,too-many-public-methods
class TestNautobotUtils(TestCase):
    """Test Nautobot Utility."""

    def setUp(self):
        """Setup."""
        site_location_type = LocationType.objects.update_or_create(name="Site")[0]
        site_location_type.content_types.set([ContentType.objects.get_for_model(VLAN)])
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
        test_location = create_location(location_name="Test-Location")
        self.assertEqual(test_location.id, self.location.id)

    def test_create_location_existing_location_with_location_id(self):
        """Test `create_location` Utility."""
        self.assertFalse(self.location.cf.get("ipfabric_site_id"))
        test_location = create_location(location_name="Test-Location", location_id="Test-Location")
        self.assertEqual(test_location.id, self.location.id)
        self.assertEqual(test_location.cf["ipfabric_site_id"], "Test-Location")

    def test_create_location_no_location_id(self):
        """Test `create_location` Utility."""
        test_location = create_location(location_name="Test-Location-new")
        self.assertEqual(test_location.name, "Test-Location-new")

    def test_create_location_with_location_id(self):
        """Test `create_location` Utility."""
        self.assertFalse(Location.objects.filter(name="Test-Location-new"))
        test_location = create_location(location_name="Test-Location-new", location_id="Test-Location-new")
        self.assertEqual(test_location.name, "Test-Location-new")
        self.assertEqual(test_location.cf["ipfabric_site_id"], "Test-Location-new")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_multiple_locations_returned(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [Location.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        test_location = create_location(location_name="Test-Location", location_id="Test-Location", logger=logger)
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Multiple Locations returned with name Test-Location")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_db_error(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_location = create_location(location_name="Test-Location", location_id="Test-Location", logger=logger)
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Unable to create a new Location named Test-Location with LocationType Site")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Location.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_validation_error(self, mock_logger, mock_tag_object, mock_location):
        """Test `create_location` Utility."""
        mock_location.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_location = create_location(location_name="Test-Location", location_id="Test-Location", logger=logger)
        self.assertEqual(test_location, None)
        logger.error.assert_called_with("Unable to create a new Location named Test-Location with LocationType Site")
        mock_tag_object.assert_not_called()

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_tag_db_error(self, mock_logger, mock_tag_object):
        """Test `create_location` Utility."""
        mock_tag_object.side_effect = [DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_location = create_location(location_name="Test-Location-new", logger=logger)
        self.assertEqual(test_location.name, "Test-Location-new")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on Location {test_location.name} with an ID of {test_location.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_location_tag_validation_error(self, mock_logger, mock_tag_object):
        """Test `create_location` Utility."""
        mock_tag_object.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_location = create_location(location_name="Test-Location-new", logger=logger)
        self.assertEqual(test_location.name, "Test-Location-new")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on Location {test_location.name} with an ID of {test_location.id}"
        )

    def test_create_device_type_object(self):
        """Test `create_device_type_object` Utility."""
        test_device_type = create_device_type_object(device_type="Test-DeviceType-New", vendor_name="Test-Manufacturer")
        self.assertEqual(test_device_type.model, "Test-DeviceType-New")

    def test_create_device_type_object_existing_device_type(self):
        """Test `create_device_type_object` Utility."""
        test_device_type = create_device_type_object(device_type="Test-DeviceType", vendor_name="Test-Manufacturer")
        self.assertEqual(test_device_type.id, self.device_type.id)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.create_manufacturer", autospec=True)
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.DeviceType.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_device_type_fail_to_get_manufacturer(self, mock_logger, mock_device_type, mock_create_manufacturer):
        """Test `create_device_type_object` Utility."""
        mock_create_manufacturer.return_value = None
        logger = mock_logger("nb_job")
        test_device_type = create_device_type_object(
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
        test_device_type = create_device_type_object(
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
        test_device_type = create_device_type_object(
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
        test_device_type = create_device_type_object(
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
        test_device_type = create_device_type_object(
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
        test_device_type = create_device_type_object(
            device_type="Test-DeviceType-new", vendor_name="Test-Manufacturer", logger=logger
        )
        self.assertEqual(test_device_type.model, "Test-DeviceType-new")
        logger.warning.assert_called_with(
            f"Unable to perform a validated_save() on DeviceType Test-DeviceType-new with an ID of {test_device_type.id}"
        )

    def test_create_manufacturer(self):
        """Test `create_manufacturer` Utility."""
        test_manufacturer = create_manufacturer(vendor_name="Test-Manufacturer")
        self.assertEqual(test_manufacturer.id, self.manufacturer.id)

    def test_create_platform_object_platform_created_no_napalm_driver(self):
        """Test `create_platform_object` Utility."""
        platform = "does_not_exist"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = create_platform_object(platform, self.manufacturer)
        self.assertEqual(self.manufacturer.id, platform_obj.manufacturer.id)
        self.assertEqual(platform_obj.name, platform)
        expected_network_driver = f"{self.manufacturer.name.lower()}_{platform}"
        self.assertEqual(platform_obj.network_driver, expected_network_driver)
        self.assertEqual(platform_obj.napalm_driver, "")

    def test_create_platform_object_platform_created_with_napalm_driver(self):
        """Test `create_platform_object` Utility."""
        manufacturer_obj, _ = Manufacturer.objects.get_or_create(name="Cisco")
        platform = "ios"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = create_platform_object(platform, manufacturer_obj)
        self.assertEqual(manufacturer_obj.id, platform_obj.manufacturer.id)
        self.assertEqual(platform_obj.name, platform)
        self.assertEqual(platform_obj.network_driver, "cisco_ios")
        self.assertEqual(platform_obj.napalm_driver, "cisco_ios")

    def test_create_platform_object_platform_created_iosxe(self):
        """Test `create_platform_object` Utility."""
        platform = "ios-xe"
        self.assertEqual(Platform.objects.filter(name=platform).count(), 0)
        platform_obj = create_platform_object(platform, self.manufacturer)
        self.assertEqual(platform_obj.network_driver, "cisco_ios")
        self.assertEqual(platform_obj.napalm_driver, "cisco_ios")

    def test_create_platform_object_existing_platform_returned(self):
        """Test `create_platform_object` Utility."""
        manufacturer_obj, _ = Manufacturer.objects.get_or_create(name="Cisco")
        platform = "ios"
        platform_obj = Platform.objects.create(name=platform, manufacturer=manufacturer_obj)
        existing_platform_obj = create_platform_object(platform, manufacturer_obj)
        self.assertEqual(platform_obj.id, existing_platform_obj.id)
        self.assertEqual(platform_obj.network_driver, "")
        self.assertEqual(platform_obj.napalm_driver, "")

    def test_get_or_create_device_role(self):
        """Test `get_or_create_device_role` Utility."""
        test_device_role = get_or_create_device_role_object("Test-Role", role_color=ColorChoices.COLOR_RED)
        self.assertEqual(test_device_role.id, self.device_role.id)

    def test_create_status(self):
        """Test `create_status` Utility."""
        test_status = create_status(status_name="Test-Status", status_color=ColorChoices.COLOR_AMBER)
        self.assertEqual(test_status.id, self.status.id)

    def test_create_status_doesnt_exist(self):
        """Test `create_status` Utility."""
        test_status = create_status(status_name="Test-Status-100", status_color=ColorChoices.COLOR_AMBER)
        self.assertEqual(test_status.id, Status.objects.get(name="Test-Status-100").id)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    def test_create_ip(self, mock_ipaddress_to_interface):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.2", "255.255.255.255")
        self.assertEqual(test_ip.host, "192.168.0.2")
        self.assertEqual(test_ip.mask_length, 32)
        self.assertEqual(test_ip.status.name, "Active")
        self.assertEqual(test_ip.parent, self.prefix)
        mock_ipaddress_to_interface.assert_not_called()

    def test_create_ip_assign_interface(self):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.2", "255.255.255.255", object_pk=self.device.interfaces.first())
        self.assertEqual(test_ip.host, "192.168.0.2")
        self.assertEqual(test_ip.mask_length, 32)
        self.assertEqual(test_ip.parent, self.prefix)
        self.assertEqual(test_ip, self.device.interfaces.first().ip_addresses.get(host="192.168.0.2"))

    def test_create_ip_alread_exists(self):
        """Test `create_ip` Utility."""
        test_ip = create_ip("192.168.0.1", "255.255.255.255")
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
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        mock_ipaddress.assert_not_called()
        logger.error.assert_called_with(
            "Multiple Statuses returned with name Active, and therefore cannot create an IPAddress of 192.168.0.1/255.255.255.255"
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
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        mock_ipaddress.assert_not_called()
        logger.error.assert_called_with(
            "Unable to find a Status with the name Active, and therefore cannot create an IPAddress of 192.168.0.1/255.255.255.255"
        )
        self.assertEqual(test_ip, None)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_multiple_ips_returned(self, mock_logger, mock_tag_object, mock_ipaddress_to_interface, mock_ip):
        """Test `create_device_type_object` Utility."""
        mock_ip.side_effect = [IPAddress.MultipleObjectsReturned]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        logger.error.assert_called_with("Multiple IPAddresses returned with the address of 192.168.0.1/255.255.255.255")
        self.assertEqual(test_ip, None)
        mock_ipaddress_to_interface.assert_not_called()
        mock_tag_object.assert_not_called()

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    def test_create_ip_db_error_on_first_try(
        self,
        mock_last_sync,
        mock_logger,
        mock_tag_object,
        mock_prefix,
        mock_ipaddress_to_interface,
        mock_ip,
        mock_status,
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [DjangoBaseDBError, ("mock_ipaddress", True)]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, "mock_ipaddress")
        mock_ipaddress_to_interface.assert_not_called()
        mock_prefix.assert_called_once()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_called_once()
        mock_tag_object.assert_called_with(nautobot_object="mock_ipaddress", custom_field=mock_last_sync)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    def test_create_ip_validation_error_on_first_try(
        self,
        mock_last_sync,
        mock_logger,
        mock_tag_object,
        mock_prefix,
        mock_ipaddress_to_interface,
        mock_ip,
        mock_status,
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [ValidationError("failure"), ("mock_ipaddress", True)]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, "mock_ipaddress")
        mock_ipaddress_to_interface.assert_not_called()
        mock_prefix.assert_called_once()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_called_once()
        mock_tag_object.assert_called_with(nautobot_object="mock_ipaddress", custom_field=mock_last_sync)

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Interface", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    def test_create_ip_db_error_on_first_try_assign_ip(
        self,
        mock_last_sync,
        mock_logger,
        mock_tag_object,
        mock_prefix,
        mock_ipaddress_to_interface,
        mock_intf,
        mock_ip,
        mock_status,
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [DjangoBaseDBError, ("mock_ipaddress", True)]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", object_pk=mock_intf, logger=logger)
        self.assertEqual(test_ip, "mock_ipaddress")
        mock_ipaddress_to_interface.assert_called_with(ip_address="mock_ipaddress", interface_id=mock_intf.pk)
        mock_ipaddress_to_interface().validated_save.assert_called_once()
        mock_prefix.assert_called_once()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_has_calls(
            [
                unittest.mock.call(nautobot_object=mock_intf, custom_field=mock_last_sync),
                unittest.mock.call(nautobot_object="mock_ipaddress", custom_field=mock_last_sync),
            ],
        )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Interface", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    def test_create_ip_validation_error_on_first_try_assign_ip(
        self,
        mock_last_sync,
        mock_logger,
        mock_tag_object,
        mock_prefix,
        mock_ipaddress_to_interface,
        mock_intf,
        mock_ip,
        mock_status,
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [ValidationError("failure"), ("mock_ipaddress", True)]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", object_pk=mock_intf, logger=logger)
        self.assertEqual(test_ip, "mock_ipaddress")
        mock_ipaddress_to_interface.assert_called_with(ip_address="mock_ipaddress", interface_id=mock_intf.pk)
        mock_ipaddress_to_interface().validated_save.assert_called_once()
        mock_prefix.assert_called_once()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_has_calls(
            [
                unittest.mock.call(nautobot_object=mock_intf, custom_field=mock_last_sync),
                unittest.mock.call(nautobot_object="mock_ipaddress", custom_field=mock_last_sync),
            ],
        )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_error_on_first_try_db_error_on_prefix(
        self, mock_logger, mock_tag_object, mock_prefix, mock_ipaddress_to_interface, mock_ip, mock_status
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.side_effect = [DjangoBaseDBError]
        mock_ip.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, None)
        mock_ipaddress_to_interface.assert_not_called()
        mock_ip.assert_called_once()
        mock_tag_object.assert_not_called()
        logger.error.assert_called_with("Unable to create a new IPAddress of 192.168.0.1/255.255.255.255. Error: ")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_error_on_first_try_validation_error_on_prefix(
        self, mock_logger, mock_tag_object, mock_prefix, mock_ipaddress_to_interface, mock_ip, mock_status
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.side_effect = [ValidationError("failure")]
        mock_ip.side_effect = [ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, None)
        mock_ipaddress_to_interface.assert_not_called()
        mock_ip.assert_called_once()
        mock_tag_object.assert_not_called()
        logger.error.assert_called_with(
            "Unable to create a new IPAddress of 192.168.0.1/255.255.255.255. Error: ['failure']"
        )

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_error_on_first_try_db_error_on_second_try(
        self, mock_logger, mock_tag_object, mock_prefix, mock_ipaddress_to_interface, mock_ip, mock_status
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [ValidationError("failure"), DjangoBaseDBError]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, None)
        mock_ipaddress_to_interface.assert_not_called()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_not_called()
        logger.error.assert_called_with("Unable to create a new IPAddress of 192.168.0.1/255.255.255.255. Error: ")

    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model", autospec=True
    )
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddressToInterface")
    @unittest.mock.patch(
        "nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create", autospec=True
    )
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_error_on_first_try_validation_error_on_second_try(
        self, mock_logger, mock_tag_object, mock_prefix, mock_ipaddress_to_interface, mock_ip, mock_status
    ):
        """Test `create_device_type_object` Utility."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_prefix.return_value = ("mock_prefix", False)
        mock_ip.side_effect = [ValidationError("failure"), ValidationError("failure")]
        logger = mock_logger("nb_job")
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip, None)
        mock_ipaddress_to_interface.assert_not_called()
        mock_ip.assert_has_calls(
            [
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
                unittest.mock.call(address="192.168.0.1/32", defaults={"status": "mock_status"}),
            ]
        )
        mock_tag_object.assert_not_called()
        logger.error.assert_called_with(
            "Unable to create a new IPAddress of 192.168.0.1/255.255.255.255. Error: ['failure']"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_interface_db_error(self, mock_logger, mock_last_sync, mock_tag_object):  # pylint: disable=unused-argument
        """Test `create_device_type_object` Utility."""
        logger = mock_logger("nb_job")
        mock_tag_object.side_effect = [DjangoBaseDBError, None]
        interface_obj = self.device.interfaces.first()
        test_ip = create_ip("192.168.0.1", "255.255.255.255", object_pk=interface_obj, logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        mock_tag_object.assert_has_calls(
            [
                unittest.mock.call(nautobot_object=interface_obj, custom_field=mock_last_sync),
                unittest.mock.call(nautobot_object=self.ip_address, custom_field=mock_last_sync),
            ]
        )
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on Interface {interface_obj.name} with an ID of {interface_obj.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_interface_validation_error(self, mock_logger, mock_last_sync, mock_tag_object):
        """Test `create_device_type_object` Utility."""
        logger = mock_logger("nb_job")
        mock_tag_object.side_effect = [ValidationError("fail"), None]
        interface_obj = self.device.interfaces.first()
        test_ip = create_ip("192.168.0.1", "255.255.255.255", object_pk=interface_obj, logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        mock_tag_object.assert_has_calls(
            [
                unittest.mock.call(nautobot_object=interface_obj, custom_field=mock_last_sync),
                unittest.mock.call(nautobot_object=self.ip_address, custom_field=mock_last_sync),
            ]
        )
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on Interface {interface_obj.name} with an ID of {interface_obj.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_ip_db_error(self, mock_logger, mock_tag_object):
        """Test `create_device_type_object` Utility."""
        logger = mock_logger("nb_job")
        mock_tag_object.side_effect = [DjangoBaseDBError]
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on IPAddress {test_ip.address} with an ID of {test_ip.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_tag_ip_validation_error(self, mock_logger, mock_tag_object):
        """Test `create_device_type_object` Utility."""
        logger = mock_logger("nb_job")
        mock_tag_object.side_effect = [ValidationError("failure")]
        test_ip = create_ip("192.168.0.1", "255.255.255.255", logger=logger)
        self.assertEqual(test_ip.id, self.ip_address.id)
        logger.warning.assert_called_with(
            f"Unable to perform validated_save() on IPAddress {test_ip.address} with an ID of {test_ip.id}"
        )

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.LAST_SYNCHRONIZED_CF_NAME")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Namespace")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_fallback_to_subnet_creation(
        self,
        mock_logger,
        mock_namespace,
        mock_status,
        mock_ip_get_or_create,
        mock_prefix_get_or_create,
        mock_last_sync,
        mock_tag_object,
    ):
        """Test `create_ip` falls back to creating prefix if IP creation fails."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_namespace.objects.get.return_value = "mock_namespace"

        # First IP create fails with Prefix.DoesNotExist (simulated)
        # Second IP create succeeds
        mock_ip_get_or_create.side_effect = [Prefix.DoesNotExist, ("mock_ip_obj", True)]

        # Prefix creation succeeds
        mock_prefix_get_or_create.return_value = ("mock_prefix", True)

        logger = mock_logger("nb_job")

        ip_addr = "10.0.0.1"
        mask = "255.255.255.0"

        # We need to import ipaddress to use in the test or trust the string matching
        import ipaddress

        result = create_ip(ip_addr, mask, logger=logger)

        self.assertEqual(result, "mock_ip_obj")

        # Verify logger info about creating prefix
        expected_network = ipaddress.ip_network("10.0.0.1/24", strict=False)
        logger.info.assert_called_with(f"Automatically creating missing prefix {expected_network} for IP {ip_addr}/24")

        # Verify Prefix was created
        mock_prefix_get_or_create.assert_called_once()
        # Verify second IP creation attempt
        self.assertEqual(mock_ip_get_or_create.call_count, 2)

    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.tag_object")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Prefix.objects.get_or_create")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.IPAddress.objects.get_or_create")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Status.objects.get_for_model")
    @unittest.mock.patch("nautobot_ssot.integrations.ipfabric.utilities.nbutils.Namespace")
    @unittest.mock.patch("logging.Logger", autospec=True)
    def test_create_ip_fallback_subnet_creation_failure(
        self,
        mock_logger,
        mock_namespace,
        mock_status,
        mock_ip_get_or_create,
        mock_prefix_get_or_create,
        mock_tag_object,
    ):
        """Test `create_ip` logs error if fallback prefix creation fails."""
        mock_status.return_value.get.return_value = "mock_status"
        mock_namespace.objects.get.return_value = "mock_namespace"

        # First IP create fails
        mock_ip_get_or_create.side_effect = Prefix.DoesNotExist

        # Prefix creation fails
        mock_prefix_get_or_create.side_effect = DjangoBaseDBError()

        logger = mock_logger("nb_job")
        ip_addr = "10.0.0.1"
        mask = "255.255.255.0"

        result = create_ip(ip_addr, mask, logger=logger)

        self.assertIsNone(result)

        logger.error.assert_called_with(f"Unable to create a new IPAddress of {ip_addr}/{mask}. Error: ")

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
        interface_details = {"name": "Test-Interface"}
        test_interface = create_interface(self.device, interface_details)
        self.assertEqual(test_interface.id, self.device.interfaces.get(name="Test-Interface").id)

    def test_create_interface_new(self):
        """Test `create_interface` Utility for new interface."""
        interface_details = {"name": "Test-Interface-New", "type": "virtual", "mtu": 1500}
        test_interface = create_interface(self.device, interface_details)
        self.assertEqual(test_interface.id, self.device.interfaces.get(name="Test-Interface-New").id)
        self.assertEqual(test_interface.mtu, 1500)
