"""Unit tests for the Nautobot DiffSync adapter class."""

from diffsync.enum import DiffSyncModelFlags
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Device, DeviceType, Location, LocationType, Manufacturer
from nautobot.extras.models import JobResult, Role, Status
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.aristacv.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.aristacv.jobs import CloudVisionDataSource


class NautobotAdapterTestCase(TransactionTestCase):
    """Test the NautobotAdapter class."""

    job_class = CloudVisionDataSource
    databases = (
        "default",
        "job_logs",
    )

    def setUp(self):
        """Create Nautobot objects to test with."""
        status_active, _ = Status.objects.get_or_create(name="Active")
        arista_manu, _ = Manufacturer.objects.get_or_create(name="Arista")

        loc_type = LocationType.objects.get_or_create(name="Site")[0]
        hq_site, _ = Location.objects.get_or_create(name="HQ", status=status_active, location_type=loc_type)

        csr_devicetype, _ = DeviceType.objects.get_or_create(model="CSR1000v", manufacturer=arista_manu)
        rtr_devicerole, _ = Role.objects.get_or_create(name="Router")

        Device.objects.get_or_create(
            name="ams01-rtr-01",
            device_type=csr_devicetype,
            status=status_active,
            role=rtr_devicerole,
            location=hq_site,
        )
        Device.objects.get_or_create(
            name="ams01-rtr-02",
            device_type=csr_devicetype,
            status=status_active,
            role=rtr_devicerole,
            location=hq_site,
        )

        self.job = self.job_class()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )
        self.nb_adapter = NautobotAdapter(job=self.job)

    def test_load_devices(self):
        """Test the load_devices() function."""
        self.nb_adapter.load_devices()
        self.assertEqual(
            {dev.name for dev in Device.objects.filter(device_type__manufacturer__name="Arista")},
            {dev.get_unique_id() for dev in self.nb_adapter.get_all("device")},
        )

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
            },
        },
    )
    def test_load_namespaces(self):
        """Test load_namespaces() loads namespaces and sets SKIP_UNMATCHED_DST when delete_namespaces_on_sync is False."""
        ns, _ = OrmNamespace.objects.get_or_create(name="TestNS")
        self.nb_adapter.load_namespaces()
        loaded = self.nb_adapter.get_all("namespace")
        self.assertIn(ns.name, {n.get_unique_id() for n in loaded})
        for model in loaded:
            self.assertEqual(model.model_flags, DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
                "aristacv_delete_namespaces_on_sync": True,
            },
        },
    )
    def test_load_namespaces_delete_on_sync(self):
        """Test load_namespaces() does not set SKIP_UNMATCHED_DST when delete_namespaces_on_sync is True."""
        ns, _ = OrmNamespace.objects.get_or_create(name="TestNSDelete")
        self.job.app_config = self.job.app_config._replace(delete_namespaces_on_sync=True)
        self.nb_adapter.load_namespaces()
        loaded = self.nb_adapter.get_all("namespace")
        self.assertIn(ns.name, {n.get_unique_id() for n in loaded})
        for model in loaded:
            self.assertNotEqual(model.model_flags, DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
            },
        },
    )
    def test_load_prefixes(self):
        """Test load_prefixes() loads prefixes and sets SKIP_UNMATCHED_DST when delete_prefixes_on_sync is False."""
        ns, _ = OrmNamespace.objects.get_or_create(name="PrefixNS")
        status_active = Status.objects.get(name="Active")
        pf = OrmPrefix.objects.create(prefix="10.1.0.0/24", namespace=ns, status=status_active)
        self.nb_adapter.load_prefixes()
        loaded = self.nb_adapter.get_all("prefix")
        expected_id = f"{pf.prefix}__{pf.namespace.name}"
        self.assertIn(expected_id, {p.get_unique_id() for p in loaded})
        for model in loaded:
            self.assertEqual(model.model_flags, DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
                "aristacv_delete_prefixes_on_sync": True,
            },
        },
    )
    def test_load_prefixes_delete_on_sync(self):
        """Test load_prefixes() does not set SKIP_UNMATCHED_DST when delete_prefixes_on_sync is True."""
        ns, _ = OrmNamespace.objects.get_or_create(name="PrefixNSDelete")
        status_active = Status.objects.get(name="Active")
        OrmPrefix.objects.create(prefix="10.2.0.0/24", namespace=ns, status=status_active)
        self.job.app_config = self.job.app_config._replace(delete_prefixes_on_sync=True)
        self.nb_adapter.load_prefixes()
        loaded = self.nb_adapter.get_all("prefix")
        expected_id = "10.2.0.0/24__PrefixNSDelete"
        our_prefix = next(p for p in loaded if p.get_unique_id() == expected_id)
        self.assertNotEqual(our_prefix.model_flags, DiffSyncModelFlags.SKIP_UNMATCHED_DST)

    @override_settings(
        PLUGINS_CONFIG={
            "nautobot_ssot": {
                "aristacv_cvaas_url": "https://www.arista.io",
                "aristacv_cvp_user": "admin",
            },
        },
    )
    def test_load_includes_namespaces_and_prefixes(self):
        """Test load() populates namespaces and prefixes."""
        OrmNamespace.objects.get_or_create(name="LoadTestNS")
        ns, _ = OrmNamespace.objects.get_or_create(name="LoadTestPrefixNS")
        status_active = Status.objects.get(name="Active")
        OrmPrefix.objects.create(prefix="10.3.0.0/24", namespace=ns, status=status_active)
        self.nb_adapter.load()
        self.assertGreater(len(self.nb_adapter.get_all("namespace")), 0)
        self.assertGreater(len(self.nb_adapter.get_all("prefix")), 0)
