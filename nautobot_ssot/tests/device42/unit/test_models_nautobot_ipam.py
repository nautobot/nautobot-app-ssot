"""Test Adapter IPAM models for Nautobot."""

from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.forms import ValidationError
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer, Platform
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Role, Status
from nautobot.ipam.models import VLAN, VRF, IPAddress, IPAddressToInterface, Namespace, Prefix

from nautobot_ssot.integrations.device42.diffsync.models.nautobot import ipam


class TestNautobotVRFGroup(TestCase):
    """Test the NautobotVRFGroup class."""

    @classmethod
    def setUpTestData(cls):
        cls.adapter = Adapter()
        cls.adapter.namespace_map = {}
        cls.adapter.vrf_map = {}
        cls.adapter.job = MagicMock()
        cls.adapter.job.logger.info = MagicMock()
        cls.vrf = VRF.objects.create(name="Test")
        cls.vrf.validated_save()

    def test_create(self):
        """Validate the NautobotVRFGroup create() method creates a VRF."""
        self.vrf.delete()
        ids = {"name": "Test"}
        attrs = {"description": "Test VRF", "tags": ["est"], "custom_fields": {"Dept": {"key": "Dept", "value": "IT"}}}
        result = ipam.NautobotVRFGroup.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, ipam.NautobotVRFGroup)
        self.adapter.job.logger.info.assert_called_once_with("Creating VRF Test.")
        namespace = Namespace.objects.get(name=ids["name"])
        self.assertEqual(namespace.name, ids["name"])
        self.assertEqual(self.adapter.namespace_map[ids["name"]], namespace.id)
        vrf = VRF.objects.get(name=ids["name"])
        self.assertEqual(self.adapter.vrf_map[ids["name"]], vrf.id)
        self.assertEqual(vrf.namespace.name, ids["name"])
        self.assertEqual(list(vrf.tags.names()), attrs["tags"])
        self.assertEqual(vrf.custom_field_data["Dept"], "IT")

    def test_update(self):
        """Validate the NautobotVRFGroup update() updates a VRF."""
        test_vrf = ipam.NautobotVRFGroup(
            name="Test", description="Test VRF", tags=[], custom_fields={}, uuid=self.vrf.id
        )
        test_vrf.adapter = self.adapter
        update_attrs = {
            "description": "Test VRF Update",
            "tags": ["Test"],
            "custom_fields": {"test": {"key": "test", "value": "test"}},
        }
        actual = ipam.NautobotVRFGroup.update(self=test_vrf, attrs=update_attrs)
        self.adapter.job.logger.info.assert_called_once_with("Updating VRF Test.")
        self.vrf.refresh_from_db()
        self.assertEqual(self.vrf.description, update_attrs["description"])
        self.assertEqual(self.vrf.custom_field_data["test"], "test")
        self.assertEqual(actual, test_vrf)
        self.assertEqual(self.vrf.description, "Test VRF Update")
        self.assertEqual(list(self.vrf.tags.names()), update_attrs["tags"])
        self.assertEqual(self.vrf.custom_field_data["test"], "test")

    def test_update_clear_tags(self):
        """Validate the NautobotVRFGroup.update() clears tags."""
        test_vrf = ipam.NautobotVRFGroup(name="Test", description="", tags=[], custom_fields={}, uuid=self.vrf.id)
        test_vrf.adapter = self.adapter
        update_attrs = {
            "tags": [],
        }
        result = test_vrf.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotVRFGroup)
        self.vrf.refresh_from_db()
        self.assertEqual(list(self.vrf.tags.names()), [])

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.PLUGIN_CFG",
        {"device42_delete_on_sync": True},
    )
    @patch("nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.OrmVRF.objects.get")
    def test_delete(self, mock_vrf):
        """Validate the NautobotVRFGroup delete() deletes a VRF."""
        vrf_group = ipam.NautobotVRFGroup(
            name="Test", description=None, tags=None, custom_fields=None, uuid=self.vrf.id
        )
        vrf_group.adapter = self.adapter
        mock_vrf.return_value = self.vrf
        self.adapter.objects_to_delete = {"vrf": []}

        vrf_group.delete()

        self.adapter.job.logger.info.assert_called_once_with("VRF Test will be deleted.")
        self.assertEqual(len(self.adapter.objects_to_delete["vrf"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["vrf"][0].id, self.vrf.id)


class TestNautobotSubnet(TestCase):
    """Test the NautobotSubnet class."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.test_vrf = VRF.objects.get_or_create(name="Test", namespace=cls.test_ns)[0]
        cls.prefix = Prefix.objects.create(prefix="10.0.0.0/24", namespace=cls.test_ns, status=cls.status_active)
        cls.adapter = Adapter()
        cls.adapter.namespace_map = {"Test": cls.test_ns.id}
        cls.adapter.vrf_map = {"Test": cls.test_vrf.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.prefix_map = {}
        cls.adapter.job = MagicMock()
        cls.adapter.job.logger.info = MagicMock()

    def test_create(self):
        """Validate the NautobotSubnet create() method creates a Prefix."""
        self.prefix.delete()
        ids = {"network": "10.0.0.0", "mask_bits": 24, "vrf": "Test"}
        attrs = {"description": "", "tags": ["Test"], "custom_fields": {"Test": {"key": "Test", "value": "test"}}}
        result = ipam.NautobotSubnet.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, ipam.NautobotSubnet)
        self.adapter.job.logger.info.assert_called_once_with("Creating Prefix 10.0.0.0/24 in VRF Test.")
        subnet = Prefix.objects.get(prefix=f"{ids['network']}/{ids['mask_bits']}", namespace=self.test_ns)
        self.assertEqual(str(subnet.prefix), f"{ids['network']}/{ids['mask_bits']}")
        self.assertEqual(self.adapter.prefix_map["Test"][f"{ids['network']}/{ids['mask_bits']}"], subnet.id)
        self.assertEqual(subnet.vrfs.all().first(), self.test_vrf)
        self.assertEqual(list(subnet.tags.names()), attrs["tags"])
        self.assertEqual(subnet.custom_field_data["Test"], "test")

    def test_create_container_type(self):
        """Validate the NautobotSubnet.create() functionality with setting Prefix to container type."""
        self.prefix.delete()
        ids = {"network": "0.0.0.0", "mask_bits": 0, "vrf": "Test"}  # nosec
        attrs = {"description": "", "tags": [], "custom_fields": {}}
        result = ipam.NautobotSubnet.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, ipam.NautobotSubnet)
        subnet = Prefix.objects.get(prefix=f"{ids['network']}/{ids['mask_bits']}", namespace=self.test_ns)
        self.assertEqual(subnet.type, "container")

    def test_update(self):
        """Validate the NautobotSubnet update() method updates a Prefix."""
        test_pf = ipam.NautobotSubnet(
            network="10.0.0.0",
            mask_bits=24,
            description=None,
            vrf="Test",
            tags=[],
            custom_fields={},
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        update_attrs = {
            "description": "Test Prefix",
            "tags": ["test"],
            "custom_fields": {"test": {"key": "test", "value": "test"}},
        }
        actual = ipam.NautobotSubnet.update(self=test_pf, attrs=update_attrs)
        self.adapter.job.logger.info.assert_called_once_with("Updating Prefix 10.0.0.0/24.")
        self.prefix.refresh_from_db()
        self.assertEqual(self.prefix.description, "Test Prefix")
        self.assertEqual(actual, test_pf)

    @patch(
        "nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.PLUGIN_CFG",
        {"device42_delete_on_sync": True},
    )
    @patch("nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.OrmPrefix.objects.get")
    def test_delete(self, mock_subnet):
        """Validate the NautobotVRFGroup delete() deletes a Prefix."""
        test_pf = ipam.NautobotSubnet(
            network="10.0.0.0",
            mask_bits=24,
            description=None,
            vrf="Test",
            tags=None,
            custom_fields=None,
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        mock_subnet.return_value = self.prefix
        self.adapter.objects_to_delete = {"subnet": []}

        test_pf.delete()

        self.adapter.job.logger.info.assert_called_once_with("Prefix 10.0.0.0/24 will be deleted.")
        self.assertEqual(len(self.adapter.objects_to_delete["subnet"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["subnet"][0].id, self.prefix.id)


class TestNautobotIPAddress(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotIPAddress class."""

    def __init__(self, *args, **kwargs):
        """Initialize shared variables."""
        super().__init__(*args, **kwargs)
        self.addr = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        status_reserved = Status.objects.get(name="Reserved")
        loc_type = LocationType.objects.get_or_create(name="Site")[0]
        loc_type.content_types.add(ContentType.objects.get_for_model(Device))
        loc_type.content_types.add(ContentType.objects.get_for_model(Prefix))
        loc = Location.objects.get_or_create(name="Test Site", location_type=loc_type, status=cls.status_active)[0]
        cisco_manu = Manufacturer.objects.get_or_create(name="Cisco")[0]
        csr1000v = DeviceType.objects.get_or_create(model="CSR1000v", manufacturer=cisco_manu)[0]
        ios_platform = Platform.objects.create(name="Cisco IOS", manufacturer=cisco_manu)
        router_role = Role.objects.create(name="Router")
        router_role.content_types.add(ContentType.objects.get_for_model(Device))
        cls.test_dev = Device.objects.create(
            name="Test Device",
            device_type=csr1000v,
            location=loc,
            platform=ios_platform,
            role=router_role,
            status=cls.status_active,
        )
        cls.test_dev2 = Device.objects.create(
            name="Device2",
            device_type=csr1000v,
            location=loc,
            platform=ios_platform,
            role=router_role,
            status=cls.status_active,
        )
        cls.dev_eth0 = Interface.objects.create(
            name="eth0", type="virtual", device=cls.test_dev, status=cls.status_active, mgmt_only=True
        )
        cls.dev2_eth0 = Interface.objects.create(
            name="eth0", type="virtual", device=cls.test_dev2, status=cls.status_active, mgmt_only=True
        )
        cls.dev2_mgmt = Interface.objects.create(
            name="mgmt0", type="virtual", device=cls.test_dev2, status=cls.status_active, mgmt_only=True
        )
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24",
            location=loc,
            namespace=cls.test_ns,
            status=cls.status_active,
        )
        cls.ids = {"address": "10.0.0.1/24", "subnet": "10.0.0.0/24"}
        cls.attrs = {
            "namespace": "Test",
            "available": False,
            "label": "Test",
            "device": "Test Device",
            "interface": "eth0",
            "primary": True,
            "tags": [],
            "custom_fields": {},
        }

        cls.adapter = Adapter()
        cls.adapter.objects_to_create = {"ports": []}
        cls.adapter.namespace_map = {"Test": cls.test_ns.id}
        cls.adapter.status_map = {"Active": cls.status_active.id, "Reserved": status_reserved.id}
        cls.adapter.prefix_map = {"10.0.0.0/24": cls.prefix.id}
        cls.adapter.device_map = {"Test Device": cls.test_dev.id}
        cls.adapter.port_map = {
            "Test Device": {"eth0": cls.dev_eth0.id},
            "Device2": {"mgmt0": cls.dev2_mgmt.id, "eth0": cls.dev2_eth0.id},
        }
        cls.adapter.ipaddr_map = {}
        cls.adapter.job = MagicMock()
        cls.adapter.job.logger.info = MagicMock()
        cls.mock_addr = ipam.NautobotIPAddress(**cls.ids, **cls.attrs)
        cls.mock_addr.adapter = cls.adapter

    def test_create_with_existing_interface(self):
        """Validate the NautobotIPAddress.create() functionality with existing Interface."""
        result = self.mock_addr.create(self.adapter, self.ids, self.attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.adapter.job.logger.info.assert_called_once_with("Creating IPAddress 10.0.0.1/24.")
        ipaddr = IPAddress.objects.get(address=self.ids["address"])
        self.assertEqual(ipaddr.parent, self.prefix)
        self.assertEqual(str(ipaddr.address), self.ids["address"])
        ipaddr_to_intf = IPAddressToInterface(ip_address=ipaddr, interface=self.dev_eth0)
        self.assertEqual(ipaddr_to_intf.interface, self.dev_eth0)
        self.assertEqual(self.adapter.ipaddr_map["Test"][self.ids["address"]], ipaddr.id)
        self.test_dev.refresh_from_db()
        self.assertEqual(self.test_dev.primary_ip4, ipaddr)

    def test_create_with_missing_prefix(self):
        """Validate the NautobotIPAddress.create() functionality with missing Prefix."""
        self.prefix.delete()
        self.adapter.job.logger.error = MagicMock()
        result = self.mock_addr.create(self.adapter, self.ids, self.attrs)
        self.adapter.job.logger.error.assert_called_once_with(
            "Unable to find prefix 10.0.0.0/24 to create IPAddress 10.0.0.1/24 for."
        )
        self.assertIsNone(result)

    def test_create_with_missing_interface(self):
        """Validate the NautobotIPAddress.create() functionality with missing Interface."""
        self.adapter.port_map = {}
        self.adapter.job.logger.debug = MagicMock()
        result = self.mock_addr.create(self.adapter, self.ids, self.attrs)
        self.adapter.job.logger.debug.assert_called_once_with("Unable to find Interface eth0 for Test Device.")
        self.assertIsInstance(result, ipam.NautobotIPAddress)

    def create_mock_ipaddress_and_assign(self):
        """Create IPAddress from mock_addr object and assign ID from IPAddress object that's created."""
        self.mock_addr.create(adapter=self.adapter, ids=self.ids, attrs=self.attrs)
        self.addr = IPAddress.objects.get(address="10.0.0.1/24")
        self.mock_addr.uuid = self.addr.id

    def test_update_changing_available(self):
        """Validate the NautobotIPAddress.update() functionality with changing available status."""
        self.create_mock_ipaddress_and_assign()
        update_attrs = {"available": True}
        self.mock_addr.update(attrs=update_attrs)
        self.addr.refresh_from_db()
        self.assertEqual(self.addr.status, self.status_active)

    def test_update_changing_label(self):
        """Validate the NautobotIPAddress.update() functionality with changing label."""
        self.create_mock_ipaddress_and_assign()
        update_attrs = {"label": "Test Update"}
        ipam.NautobotIPAddress.update(self=self.mock_addr, attrs=update_attrs)
        self.addr.refresh_from_db()
        self.assertEqual(self.addr.description, update_attrs["label"])

    def test_update_changing_device_and_interface(self):
        """Validate the NautobotIPAddress.update() functionality with changing Device and Interface."""
        self.create_mock_ipaddress_and_assign()
        update_attrs = {
            "device": "Device2",
            "interface": "mgmt0",
            "primary": True,
        }
        result = ipam.NautobotIPAddress.update(self=self.mock_addr, attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.test_dev2.refresh_from_db()
        self.assertEqual(self.test_dev2.primary_ip4, self.addr)
        ip_to_intfs = IPAddressToInterface.objects.filter(ip_address=self.addr, interface=self.dev2_mgmt)
        self.assertEqual(len(ip_to_intfs), 1)

    def test_update_changing_device(self):
        """Validate the NautobotIPAddress.update() functionality with changing Device."""
        self.create_mock_ipaddress_and_assign()
        update_attrs = {"device": "Device2"}
        result = self.mock_addr.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.addr.refresh_from_db()
        self.test_dev2.refresh_from_db()
        self.assertEqual(self.test_dev2.primary_ip4, self.addr)
        ip_to_intf = IPAddressToInterface.objects.filter(ip_address=self.addr, interface=self.dev2_eth0)
        self.assertEqual(len(ip_to_intf), 1)

    def test_update_changing_interface(self):
        """Validate the NautobotIPAddress.update() functionality with changing Interface."""
        self.mock_addr.device = "Device2"
        self.create_mock_ipaddress_and_assign()

        update_attrs = {"interface": "mgmt0"}
        result = self.mock_addr.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.addr.refresh_from_db()
        self.dev2_mgmt.refresh_from_db()
        self.assertEqual(self.addr.interfaces.first(), self.dev2_mgmt)

    def test_update_changing_primary(self):
        """Validate the NautobotIPAddress.update() functionality with making an IPAddress primary."""
        self.mock_addr.primary = False
        self.create_mock_ipaddress_and_assign()

        update_attrs = {"primary": True}
        result = self.mock_addr.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.addr.refresh_from_db()
        self.test_dev.refresh_from_db()
        self.assertEqual(self.test_dev.primary_ip4, self.addr)

    def test_update_changing_tags(self):
        """Validate the NautobotIPAddress.update() functionality with updating Tags on IPAddress."""
        self.create_mock_ipaddress_and_assign()

        update_attrs = {"tags": ["Test", "Test2"]}
        result = self.mock_addr.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.addr.refresh_from_db()
        self.assertEqual(list(self.addr.tags.names()), update_attrs["tags"])

    def test_update_changing_custom_fields(self):
        """Validate the NautobotIPAddress.update() functionality with changing CustomFields on IPAddress."""
        self.create_mock_ipaddress_and_assign()

        update_attrs = {"custom_fields": {"New CF": {"key": "New CF", "value": "Test"}}}
        result = self.mock_addr.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotIPAddress)
        self.addr.refresh_from_db()
        self.assertEqual(self.addr.custom_field_data["New_CF"], "Test")

    @patch("nautobot_ssot.integrations.device42.diffsync.models.nautobot.ipam.OrmIPAddress.objects.get")
    def test_update_handling_validation_error(self, mock_ip_get):
        """Validate how the NautobotIPAddress.update() handles a ValidationError."""
        mock_ip = MagicMock()
        mock_ip.address = "10.0.0.1/24"
        self.mock_addr.primary = False
        mock_ip.validated_save = MagicMock()
        mock_ip.validated_save.side_effect = ValidationError(message="Error")
        mock_ip_get.return_value = mock_ip
        self.adapter.job.logger.warning = MagicMock()
        result = self.mock_addr.update(attrs={})
        self.assertIsNone(result)
        self.adapter.job.logger.warning.assert_called_once_with(
            "Unable to update IP Address 10.0.0.1/24 with {}. ['Error']"
        )


class TestNautobotVLAN(TestCase):
    """Test the NautobotVLAN class."""

    def __init__(self, *args, **kwargs):
        """Initialize shared variables."""
        super().__init__(*args, **kwargs)
        self.vlan = None

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")

        site_type = LocationType.objects.get_or_create(name="Site")[0]
        site_type.content_types.add(ContentType.objects.get_for_model(Device))
        site_type.content_types.add(ContentType.objects.get_for_model(VLAN))

        cls.test_site = Location.objects.create(name="HQ", location_type=site_type, status=cls.status_active)
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.logger.info = MagicMock()
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.site_map = {"HQ": cls.test_site.id}
        cls.adapter.vlan_map = {"HQ": {}}
        cls.ids = {
            "vlan_id": 1,
            "building": None,
        }
        cls.attrs = {
            "name": "Test",
            "description": "Test VLAN",
            "tags": [],
            "custom_fields": {},
        }
        cls.mock_vlan = ipam.NautobotVLAN(**cls.ids, **cls.attrs)
        cls.mock_vlan.adapter = cls.adapter

    def test_create_with_undefined_building(self):
        """Validate the NautobotVLAN.create() functionality with an undefined building."""
        self.adapter.site_map = {}
        result = self.mock_vlan.create(adapter=self.adapter, ids=self.ids, attrs=self.attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        self.adapter.job.logger.info.assert_called_once_with("Creating VLAN 1 Test for Global")
        vlan = VLAN.objects.get(vid=1)
        self.assertIsNone(vlan.location)
        self.assertEqual(vlan.name, self.attrs["name"])
        self.assertEqual(vlan.description, self.attrs["description"])
        self.assertEqual(self.adapter.vlan_map["Global"][1], vlan.id)

    def test_create_with_defined_building(self):
        """Validate the NautobotVLAN.create() functionality with a defined building."""
        self.ids["building"] = "HQ"
        result = self.mock_vlan.create(adapter=self.adapter, ids=self.ids, attrs=self.attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        self.adapter.job.logger.info.assert_called_once_with("Creating VLAN 1 Test for HQ")
        vlan = VLAN.objects.get(vid=1)
        self.assertEqual(vlan.location, self.test_site)
        self.assertEqual(vlan.name, self.attrs["name"])
        self.assertEqual(vlan.description, self.attrs["description"])
        self.assertEqual(self.adapter.vlan_map["HQ"][1], vlan.id)

    def create_mock_vlan_and_assign(self):
        """Create IPAddress from mock_addr object and assign ID from IPAddress object that's created."""
        self.mock_vlan.create(adapter=self.adapter, ids=self.ids, attrs=self.attrs)
        self.vlan = VLAN.objects.get(vid=1)
        self.mock_vlan.uuid = self.vlan.id

    def test_update_vlan_name(self):
        """Validate the NautobotVLAN.update() functionality with a new VLAN name."""
        self.create_mock_vlan_and_assign()
        update_attrs = {"name": "Test2"}
        result = self.mock_vlan.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        self.adapter.job.logger.info.assert_called_with("Updating VLAN Test 1 for Global.")
        vlan = VLAN.objects.get(vid=1)
        self.assertEqual(vlan.name, "Test2")

    def test_update_vlan_desscription(self):
        """Validate the NautobotVLAN.update() functionality with a new description."""
        self.create_mock_vlan_and_assign()
        update_attrs = {"description": "DMZ VLAN"}
        result = self.mock_vlan.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        vlan = VLAN.objects.get(vid=1)
        self.assertEqual(vlan.description, "DMZ VLAN")

    def test_update_vlan_custom_fields(self):
        """Validate the NautobotVLAN.update() functionality with adding CustomFields."""
        self.create_mock_vlan_and_assign()
        update_attrs = {"custom_fields": {"Test": {"key": "Test", "value": "test"}}}
        result = self.mock_vlan.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        vlan = VLAN.objects.get(vid=1)
        self.assertEqual(vlan.custom_field_data["Test"], "test")

    def test_update_vlan_tags(self):
        """Validate the NautobotVLAN.update() functionality with adding tags."""
        self.create_mock_vlan_and_assign()
        update_attrs = {"tags": ["Test", "Test2"]}
        result = self.mock_vlan.update(attrs=update_attrs)
        self.assertIsInstance(result, ipam.NautobotVLAN)
        vlan = VLAN.objects.get(vid=1)
        self.assertEqual(list(vlan.tags.names()), update_attrs["tags"])
