"""Test Nautobot Utilities."""
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from nautobot.dcim.models import DeviceType, Manufacturer, Location, LocationType
from nautobot.dcim.models.devices import Device
from nautobot.extras.models.statuses import Status
from nautobot.ipam.models import VLAN, IPAddress, Prefix, get_default_namespace
from nautobot.core.choices import ColorChoices
from nautobot.extras.models import Role

from nautobot_ssot.integrations.ipfabric.utilities import (  # create_ip,; create_interface,; create_location,
    get_or_create_device_role_object,
    create_device_type_object,
    create_location,
    create_manufacturer,
    create_status,
    create_vlan,
)


# pylint: disable=too-many-instance-attributes
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
        prefix = Prefix.objects.get_or_create(
            prefix="192.168.0.0/16", namespace=get_default_namespace(), status=status_active
        )[0]
        self.ip_address = IPAddress.objects.create(address="192.168.0.1/32", status=status_active, parent=prefix)

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

    # def test_create_location_exception(self):
    #     """Test `create_location` Utility exception."""
    #     location = create_location(
    #         location_name="Test-Location-100",
    #         location_id=123456,
    #     )
    #     self.assertEqual(Location.objects.get(name="Test-Location-100").pk, location.pk)

    def test_create_device_type_object(self):
        """Test `create_device_type_object` Utility."""
        test_device_type = create_device_type_object(device_type="Test-DeviceType", vendor_name="Test-Manufacturer")
        self.assertEqual(test_device_type.id, self.device_type.id)

    def test_create_manufacturer(self):
        """Test `create_manufacturer` Utility."""
        test_manufacturer = create_manufacturer(vendor_name="Test-Manufacturer")
        self.assertEqual(test_manufacturer.id, self.manufacturer.id)

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

    # def test_create_ip(self):
    #     """Test `create_ip` Utility."""
    #     test_ip = create_ip("192.168.0.1", "255.255.255.255")
    #     self.assertEqual(test_ip.id, self.ip_address.id)

    # def test_create_ip_device_add(self):
    #     """Test `create_ip` adding to device Utility."""
    #     test_ip = create_ip("192.168.0.1", "255.255.255.255", object_pk=self.device.id)
    #     self.assertEqual(test_ip.id, self.ip_address.id)

    # def test_create_interface(self):
    #     """Test `create_interface` Utility."""
    #     interface_details = {"name": "Test-Interface"}
    #     test_interface = create_interface(self.device, interface_details)
    #     self.assertEqual(test_interface.id, self.device.interfaces.get(name="Test-Interface").id)
