"""Unit tests for the Nautobot DiffSync adapter."""

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, DeviceType, Interface, Location, LocationType, Manufacturer, Platform
from nautobot.extras.models import JobResult, Note, Role, Status
from nautobot.ipam.models import IPAddress, IPAddressToInterface, Namespace, Prefix

from nautobot_ssot.integrations.meraki.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.meraki.jobs import MerakiDataSource

User = get_user_model()


class NautobotDiffSyncTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):  # pylint: disable=too-many-locals
        """Per-test-case data setup."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")

        self.region_type = LocationType.objects.get_or_create(name="Region", defaults={"nestable": True})[0]
        global_region = Location.objects.create(
            name="Global Region",
            location_type=self.region_type,
            status=self.status_active,
        )
        global_region.validated_save()
        self.site_type = LocationType.objects.get_or_create(name="Site")[0]
        self.site_type.content_types.add(ContentType.objects.get_for_model(Device))
        self.site_type.content_types.add(ContentType.objects.get_for_model(Prefix))
        site1 = Location.objects.create(
            name="Lab",
            location_type=self.site_type,
            status=self.status_active,
            time_zone="America/Chicago",
        )
        site1.validated_save()
        site1.tags.set(["Test"])
        site1.validated_save()
        site_note = Note.objects.create(
            note="Test",
            user=User.objects.first(),
            assigned_object_type=ContentType.objects.get_for_model(Location),
            assigned_object_id=site1.id,
        )
        site_note.validated_save()

        cisco_manu = Manufacturer.objects.get_or_create(name="Cisco Meraki")[0]
        cisco_manu.validated_save()

        meraki_plat = Platform.objects.get_or_create(name="Cisco Meraki")[0]

        mx84 = DeviceType.objects.create(model="MX84", manufacturer=cisco_manu)
        mx84.validated_save()

        core_role = Role.objects.get_or_create(name="CORE")[0]
        core_role.content_types.add(ContentType.objects.get_for_model(Device))

        lab01 = Device.objects.create(
            name="Lab01",
            serial="ABC-123-456",
            status=self.status_active,
            role=core_role,
            device_type=mx84,
            platform=meraki_plat,
            location=site1,
        )
        lab01.validated_save()
        lab01.custom_field_data["system_of_record"] = "Meraki SSoT"
        lab01.custom_field_data["os_version"] = "10.1.1"
        lab01.validated_save()
        lab01_note = Note.objects.create(
            note="Lab01 Test Note",
            user=User.objects.first(),
            assigned_object_type=ContentType.objects.get_for_model(Device),
            assigned_object_id=lab01.id,
        )
        lab01_note.validated_save()

        lab01_mgmt = Interface.objects.create(
            name="wan1",
            device=lab01,
            enabled=True,
            mode="access",
            mgmt_only=True,
            type="1000base-t",
            status=self.status_active,
        )
        lab01_mgmt.validated_save()
        lab01_mgmt.custom_field_data["system_of_record"] = "Meraki SSoT"
        lab01_mgmt.validated_save()

        test_ns = Namespace.objects.create(name="Test")
        lab_prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", location=site1, namespace=test_ns, status=self.status_active
        )
        lab01_mgmt_ip = IPAddress.objects.create(address="10.0.0.1/24", parent=lab_prefix, status=self.status_active)
        lab_prefix.custom_field_data["system_of_record"] = "Meraki SSoT"
        lab_prefix.validated_save()
        lab01_mgmt_ip.custom_field_data["system_of_record"] = "Meraki SSoT"
        lab01_mgmt_ip.validated_save()
        IPAddressToInterface.objects.create(ip_address=lab01_mgmt_ip, interface=lab01_mgmt)

        job = MerakiDataSource()
        job.logger.warning = MagicMock()
        job.parent_location = global_region
        job.hostname_mapping = []
        job.devicetype_mapping = [("MS", "Switch"), ("MX", "Firewall")]
        job.network_loctype = self.site_type
        job.tenant = None
        job.job_result = JobResult.objects.create(name=job.class_path, task_name="fake task", worker="default")
        self.nb_adapter = NautobotAdapter(job=job, sync=None)

    def test_data_loading(self):
        """Test the load() function."""
        self.nb_adapter.load()
        self.assertEqual(
            {f"{site.name}__None" for site in Location.objects.filter(location_type=self.site_type)},
            {site.get_unique_id() for site in self.nb_adapter.get_all("network")},
        )
        self.assertEqual(
            {dev.name for dev in Device.objects.all()},
            {dev.get_unique_id() for dev in self.nb_adapter.get_all("device")},
        )
        self.assertEqual({"wan1__Lab01"}, {port.get_unique_id() for port in self.nb_adapter.get_all("port")})
        self.assertEqual(
            {f"{pf.prefix}__{pf.namespace.name}" for pf in Prefix.objects.all()},
            {pf.get_unique_id() for pf in self.nb_adapter.get_all("prefix")},
        )
        self.assertEqual(
            {f"{ipaddr.host}__None" for ipaddr in IPAddress.objects.all()},
            {ipaddr.get_unique_id() for ipaddr in self.nb_adapter.get_all("ipaddress")},
        )
        self.assertEqual(
            {"10.0.0.1__Lab01__Test__wan1"},
            {map.get_unique_id() for map in self.nb_adapter.get_all("ipassignment")},
        )
