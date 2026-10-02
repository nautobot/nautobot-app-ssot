"""Unit tests for Nautobot IPAM model CRUD functions."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from diffsync import Adapter
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import (
    Device,
    DeviceType,
    Location,
    LocationType,
    Manufacturer,
    Platform,
    SoftwareVersion,
)
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Note, Role, Status
from nautobot.ipam.models import IPAddress, Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.meraki.diffsync.models.nautobot import (
    NautobotDevice,
    NautobotIPAddress,
    NautobotNetwork,
    NautobotOSVersion,
    NautobotPrefix,
)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotPrefix(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotPrefix class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        cls.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=cls.status_active)[0]
        cls.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=cls.status_active
        )[0]
        cls.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        cls.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=cls.test_ns, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.adapter = Adapter()
        cls.adapter.namespace_map = {"Test": cls.test_ns.id, "Update": cls.update_site.id}
        cls.adapter.site_map = {"Test": cls.test_site, "Update": cls.update_site}
        cls.adapter.tenant_map = {"Test": cls.test_tenant.id, "Update": cls.update_tenant.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.prefix_map = {}
        cls.adapter.objects_to_create = {"prefixes": []}
        cls.adapter.objects_to_delete = {"prefixes": []}

    def test_create(self):
        """Validate the NautobotPrefix create() method creates a Prefix."""
        self.prefix.delete()
        ids = {"prefix": "10.0.0.0/24", "namespace": "Test"}
        attrs = {"tenant": "Test"}
        result = NautobotPrefix.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotPrefix)
        self.assertEqual(len(self.adapter.objects_to_create["prefixes"]), 1)
        subnet = self.adapter.objects_to_create["prefixes"][0]
        self.assertEqual(str(subnet.prefix), ids["prefix"])
        self.assertEqual(self.adapter.prefix_map[ids["prefix"]], subnet.id)
        self.assertEqual(subnet.custom_field_data["system_of_record"], "Meraki SSoT")

    def test_update(self):
        """Validate the NautobotPrefix update() method updates a Prefix."""
        test_pf = NautobotPrefix(
            prefix="10.0.0.0/24",
            namespace="Test",
            tenant="Test",
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        update_attrs = {"tenant": "Update"}
        actual = NautobotPrefix.update(self=test_pf, attrs=update_attrs)
        self.prefix.refresh_from_db()
        self.assertEqual(self.prefix.tenant, self.update_tenant)
        self.assertEqual(actual, test_pf)

    @patch("nautobot_ssot.integrations.meraki.diffsync.models.nautobot.OrmPrefix.objects.get")
    def test_delete(self, mock_prefix):
        """Validate the NautobotPrefix delete() deletes a Prefix."""
        test_pf = NautobotPrefix(
            prefix="10.0.0.0/24",
            namespace="Test",
            tenant="Test",
            uuid=self.prefix.id,
        )
        test_pf.adapter = self.adapter
        mock_prefix.return_value = self.prefix
        test_pf.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["prefixes"][0].id, self.prefix.id)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotIPAddress(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotIPAddress class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        cls.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=cls.status_active)[0]
        cls.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=cls.status_active
        )[0]
        cls.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        cls.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        cls.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        cls.prefix = Prefix(
            prefix="10.0.0.0/24", namespace=cls.test_ns, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.debug = True
        cls.adapter.job.logger = MagicMock()
        cls.adapter.job.logger.debug = MagicMock()
        cls.adapter.job.logger.error = MagicMock()
        cls.adapter.namespace_map = {"Test": cls.test_ns.id, "Update": cls.update_site.id}
        cls.adapter.site_map = {"Test": cls.test_site, "Update": cls.update_site}
        cls.adapter.tenant_map = {"Test": cls.test_tenant.id, "Update": cls.update_tenant.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.ipaddr_map = {}
        cls.adapter.prefix_map = {"10.0.0.0/24": cls.prefix.id}
        cls.adapter.objects_to_create = {"ipaddrs": [], "ipaddrs-to-prefixes": [], "prefixes": []}
        cls.adapter.objects_to_delete = {"ipaddrs": []}
        cls.test_ipaddr = IPAddress(
            address="10.0.0.1/24", parent=cls.prefix, status=cls.status_active, tenant=cls.test_tenant
        )
        cls.test_ip = NautobotIPAddress(
            host="10.0.0.1",
            mask_length=24,
            prefix="10.0.0.0/24",
            tenant="Test",
            uuid=cls.test_ipaddr.id,
        )
        cls.test_ip.adapter = cls.adapter

    def test_create(self):
        """Validate the NautobotAddress create() method creates an IPAddress."""
        self.test_ipaddr.delete()
        ids = {"host": "10.0.0.1", "tenant": "Test"}
        attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        result = NautobotIPAddress.create(self.adapter, ids, attrs)
        self.assertIsInstance(result, NautobotIPAddress)
        self.assertEqual(len(self.adapter.objects_to_create["ipaddrs"]), 1)
        ipaddr = self.adapter.objects_to_create["ipaddrs"][0]
        self.assertEqual(str(ipaddr.host), ids["host"])
        self.assertEqual(ipaddr.mask_length, attrs["mask_length"])
        self.assertEqual(self.adapter.objects_to_create["ipaddrs-to-prefixes"][0], (ipaddr, self.prefix.id))
        self.assertEqual(self.adapter.ipaddr_map["Test"][ids["host"]], ipaddr.id)

    def test_update_mask_length(self):
        """Validate the NautobotAddress update() method updates an IPAddress mask length."""
        self.prefix.validated_save()
        self.test_ipaddr.validated_save()
        update_attrs = {"mask_length": 32}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.adapter.job.logger.debug.assert_called_once_with(
            ("Updating IPAddress 10.0.0.1/24 in Nautobot with {'mask_length': 32}.")
        )
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.mask_length, 32)
        self.assertIsInstance(actual, NautobotIPAddress)

    def test_update_to_existing_prefix(self):
        """Validate the NautobotAddress update() method updates an IPAddress to an existing prefix."""
        host_prefix = Prefix.objects.create(
            prefix="10.0.0.1/32", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.address = "10.0.0.1/32"
        self.test_ipaddr.parent = host_prefix
        self.test_ipaddr.validated_save()
        self.prefix.validated_save()
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.adapter.job.logger.debug.assert_called_once_with(
            "Updating IPAddress 10.0.0.1/32 in Nautobot with {'mask_length': 24, 'prefix': '10.0.0.0/24'}."
        )
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.parent.prefix, self.prefix.prefix)
        self.assertEqual(self.test_ipaddr.parent.type, "pool")
        self.assertIsInstance(actual, NautobotIPAddress)

    def test_update_to_new_prefix(self):
        """Validate the NautobotAddress update() method updates an IPAddress to a new prefix."""
        host_prefix = Prefix.objects.create(
            prefix="10.0.0.1/32", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.address = "10.0.0.1/32"
        self.test_ipaddr.mask_length = 32
        self.test_ipaddr.parent = host_prefix
        self.test_ipaddr.validated_save()
        self.prefix.delete()
        Prefix.objects.create(
            prefix="0.0.0.0/0", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        net_pf = Prefix(
            prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.adapter.prefix_map = {"10.0.0.0/24": net_pf.id}
        self.adapter.objects_to_create["prefixes"] = [net_pf]
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsInstance(actual, NautobotIPAddress)
        self.test_ipaddr.refresh_from_db()
        self.assertEqual(self.test_ipaddr.parent.type, "pool")
        self.assertEqual(self.test_ipaddr.parent.prefix, net_pf.prefix)

    def test_update_to_missing_prefix(self):
        """Validate the NautobotAddress update() method handles a missing prefix."""
        self.prefix.delete()
        global_pf = Prefix.objects.create(
            prefix="0.0.0.0/0", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.test_ipaddr.parent = global_pf
        self.test_ipaddr.validated_save()
        update_attrs = {"mask_length": 24, "prefix": "10.0.0.0/24"}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsNone(actual)
        self.adapter.job.logger.error.assert_called_once_with("New parent Prefix 10.0.0.0/24 not found.")

    def test_update_to_prefix_missing_from_map(self):
        """Validate the NautobotAddress update() method handles a prefix missing from the prefix_map."""
        self.prefix.validated_save()
        self.test_ipaddr.validated_save()
        update_attrs = {"prefix": "10.100.0.0/8", "mask_length": 24}
        self.adapter.prefix_map = {}
        actual = NautobotIPAddress.update(self=self.test_ip, attrs=update_attrs)
        self.assertIsNone(actual)
        self.adapter.job.logger.error.assert_called_once_with("Prefix 10.100.0.0/8 not found in Nautobot.")


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotOSVersion(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotOSVersion class."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Device))
        cls.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=cls.status_active)[0]
        manufacturer = Manufacturer.objects.get_or_create(name="Cisco Meraki")[0]
        cls.platform = Platform.objects.get_or_create(name="Cisco Meraki", manufacturer=manufacturer)[0]
        devicetype = DeviceType.objects.get_or_create(model="MX84", manufacturer=manufacturer)[0]
        role = Role.objects.get_or_create(name="Firewall")[0]
        role.content_types.add(ContentType.objects.get_for_model(Device))
        cls.old_version = SoftwareVersion.objects.create(
            version="15.42", platform=cls.platform, status=cls.status_active
        )
        # A Device still referencing the SoftwareVersion is what makes an immediate delete raise ProtectedError.
        cls.device = Device.objects.create(
            name="HQ01",
            device_type=devicetype,
            role=role,
            location=cls.test_site,
            status=cls.status_active,
            software_version=cls.old_version,
        )
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.objects_to_delete = defaultdict(list)

    def _build_osversion(self):
        """Build a NautobotOSVersion for the old SoftwareVersion, bound to the test adapter."""
        osversion = NautobotOSVersion(version="15.42", uuid=self.old_version.id)
        osversion.adapter = self.adapter
        return osversion

    def test_delete_defers_removal(self):
        """Validate delete() queues the SoftwareVersion instead of removing it while a Device still references it."""
        osversion = self._build_osversion()

        actual = osversion.delete()

        self.assertEqual(actual, osversion)
        self.assertEqual([self.old_version.id], [ver.id for ver in self.adapter.objects_to_delete["osversions"]])
        # Deleting inline here is what raised ProtectedError, so the record must survive the delete() call.
        self.assertTrue(SoftwareVersion.objects.filter(id=self.old_version.id).exists())

    @patch("nautobot_ssot.integrations.meraki.diffsync.models.nautobot.SoftwareVersion.objects.get")
    def test_delete_skips_validated_software(self, mock_get):
        """Validate delete() does not queue a SoftwareVersion that is used by a ValidatedSoftware."""
        mock_version = MagicMock()
        mock_version.version = "15.42"
        mock_version.platform.name = "Cisco Meraki"
        mock_version.validatedsoftwarelcm_set.count.return_value = 1
        mock_get.return_value = mock_version

        self._build_osversion().delete()

        self.assertEqual([], self.adapter.objects_to_delete["osversions"])
        self.adapter.job.logger.warning.assert_called_once_with(
            "SoftwareVersion 15.42 for Cisco Meraki is used with a ValidatedSoftware so won't be deleted."
        )


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNotesSync(TestCase):  # pylint: disable=too-many-instance-attributes
    """Test that Notes on Networks and Devices track the note in Meraki."""

    databases = ("default", "job_logs")

    @classmethod
    def setUpTestData(cls):
        """Configure common variables and objects for tests."""
        super().setUpTestData()
        populate_status_choices()
        cls.status_active = Status.objects.get(name="Active")
        cls.site_lt = LocationType.objects.get_or_create(name="Site")[0]
        cls.site_lt.content_types.add(ContentType.objects.get_for_model(Device))
        cls.test_site = Location.objects.get_or_create(
            name="Test", location_type=cls.site_lt, status=cls.status_active
        )[0]
        manufacturer = Manufacturer.objects.get_or_create(name="Cisco Meraki")[0]
        Platform.objects.get_or_create(name="Cisco Meraki", manufacturer=manufacturer)
        devicetype = DeviceType.objects.get_or_create(model="MX84", manufacturer=manufacturer)[0]
        role = Role.objects.get_or_create(name="Firewall")[0]
        role.content_types.add(ContentType.objects.get_for_model(Device))
        cls.device = Device.objects.create(
            name="HQ01",
            device_type=devicetype,
            role=role,
            location=cls.test_site,
            status=cls.status_active,
        )
        cls.location_ct = ContentType.objects.get_for_model(Location)
        cls.device_ct = ContentType.objects.get_for_model(Device)
        cls.user = get_user_model().objects.create(username="testuser")
        cls.adapter = Adapter()
        cls.adapter.job = MagicMock()
        cls.adapter.job.user = cls.user
        cls.adapter.contenttype_map = {"location": cls.location_ct.id, "device": cls.device_ct.id}
        cls.adapter.tenant_map = {}
        cls.adapter.devicerole_map = {"Firewall": role.id}
        cls.adapter.devicetype_map = {"MX84": devicetype.id}
        cls.adapter.status_map = {"Active": cls.status_active.id}
        cls.adapter.version_map = {}

    def _add_note(self, nautobot_object, contenttype, note="Original note"):
        """Attach a Note to the passed object the way a prior sync would have."""
        new_note = Note(
            note=note,
            user=self.user,
            assigned_object_type=contenttype,
            assigned_object_id=nautobot_object.id,
        )
        new_note.validated_save()
        return new_note

    @staticmethod
    def _note_texts(nautobot_object, contenttype):
        """Return the text of every Note assigned to the passed object, oldest first."""
        return [
            note.note
            for note in Note.objects.filter(
                assigned_object_type=contenttype, assigned_object_id=nautobot_object.id
            ).order_by("created")
        ]

    def _build_network(self):
        """Build a NautobotNetwork for the test Location, bound to the test adapter."""
        network = NautobotNetwork(
            name="Test", parent=None, timezone=None, notes="Original note", uuid=self.test_site.id
        )
        network.adapter = self.adapter
        return network

    def _build_device(self):
        """Build a NautobotDevice for the test Device, bound to the test adapter."""
        device = NautobotDevice(
            name="HQ01",
            controller_group=None,
            notes="Original note",
            serial="",
            status="Active",
            role="Firewall",
            model="MX84",
            network="Test",
            tenant=None,
            version=None,
            uuid=self.device.id,
        )
        device.adapter = self.adapter
        return device

    def test_network_update_removes_note_when_cleared_in_meraki(self):
        """Validate a Network note deleted in Meraki is removed from Nautobot instead of being re-diffed forever."""
        self._add_note(self.test_site, self.location_ct)

        self._build_network().update(attrs={"notes": ""})

        self.assertEqual([], self._note_texts(self.test_site, self.location_ct))

    def test_device_update_removes_note_when_cleared_in_meraki(self):
        """Validate a Device note deleted in Meraki is removed from Nautobot instead of being re-diffed forever."""
        self._add_note(self.device, self.device_ct)

        self._build_device().update(attrs={"notes": ""})

        self.assertEqual([], self._note_texts(self.device, self.device_ct))

    def test_network_update_changes_note_in_place(self):
        """Validate a changed Network note updates the existing Note rather than stacking a second one."""
        self._add_note(self.test_site, self.location_ct)

        self._build_network().update(attrs={"notes": "Updated note"})

        self.assertEqual(["Updated note"], self._note_texts(self.test_site, self.location_ct))

    def test_device_update_changes_note_in_place(self):
        """Validate a changed Device note updates the existing Note rather than stacking a second one."""
        self._add_note(self.device, self.device_ct)

        self._build_device().update(attrs={"notes": "Updated note"})

        self.assertEqual(["Updated note"], self._note_texts(self.device, self.device_ct))

    def test_network_update_adds_note_when_missing(self):
        """Validate a Network note added in Meraki creates a Note when Nautobot has none."""
        self._build_network().update(attrs={"notes": "Brand new note"})

        self.assertEqual(["Brand new note"], self._note_texts(self.test_site, self.location_ct))

    def test_device_update_adds_note_when_missing(self):
        """Validate a Device note added in Meraki creates a Note when Nautobot has none."""
        self._build_device().update(attrs={"notes": "Brand new note"})

        self.assertEqual(["Brand new note"], self._note_texts(self.device, self.device_ct))

    def test_update_without_notes_attr_leaves_note_alone(self):
        """Validate a Device update that doesn't involve notes leaves the existing Note untouched."""
        self._add_note(self.device, self.device_ct)

        self._build_device().update(attrs={"serial": "XYZ-987"})

        self.assertEqual(["Original note"], self._note_texts(self.device, self.device_ct))
