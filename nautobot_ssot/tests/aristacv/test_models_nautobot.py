"""Unit tests for Arista CV Nautobot DiffSync model delete behavior."""

from collections import defaultdict
from unittest.mock import MagicMock, patch

from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import Status
from nautobot.ipam.models import Namespace as OrmNamespace
from nautobot.ipam.models import Prefix as OrmPrefix

from nautobot_ssot.integrations.aristacv.diffsync.models.nautobot import NautobotNamespace, NautobotPrefix
from nautobot_ssot.integrations.aristacv.utils.nautobot import get_config


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotNamespaceDelete(TransactionTestCase):
    """Test NautobotNamespace.delete() conditional on delete_namespaces_on_sync."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up adapter with job and app_config."""
        super().setUp()
        self.adapter = MagicMock()
        self.adapter.objects_to_delete = defaultdict(list)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.app_config = get_config()._replace(delete_namespaces_on_sync=False)

    def test_namespace_delete_when_delete_on_sync_false(self):
        """When delete_namespaces_on_sync is False, delete() does not append to objects_to_delete."""
        ns = OrmNamespace.objects.create(name="NoDeleteNS")
        model = NautobotNamespace(name="NoDeleteNS", uuid=ns.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["namespaces"]), 0)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmNamespace.objects.get")
    def test_namespace_delete_when_delete_on_sync_true(self, mock_ns_get):
        """When delete_namespaces_on_sync is True, delete() appends namespace to objects_to_delete."""
        ns = OrmNamespace.objects.create(name="DeleteNS")
        mock_ns_get.return_value = ns
        self.adapter.job.app_config = get_config()._replace(delete_namespaces_on_sync=True)
        model = NautobotNamespace(name="DeleteNS", uuid=ns.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["namespaces"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["namespaces"][0].id, ns.id)


@override_settings(
    PLUGINS_CONFIG={
        "nautobot_ssot": {
            "aristacv_cvaas_url": "https://www.arista.io",
            "aristacv_cvp_user": "admin",
        },
    },
)
class TestNautobotPrefixDelete(TransactionTestCase):
    """Test NautobotPrefix.delete() conditional on delete_prefixes_on_sync."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Set up adapter with job and app_config."""
        super().setUp()
        self.adapter = MagicMock()
        self.adapter.objects_to_delete = defaultdict(list)
        self.adapter.job = MagicMock()
        self.adapter.job.debug = False
        self.adapter.job.app_config = get_config()._replace(delete_prefixes_on_sync=False)
        self.ns = OrmNamespace.objects.create(name="PrefixTestNS")
        self.status_active = Status.objects.get(name="Active")
        self.prefix = OrmPrefix.objects.create(prefix="10.99.0.0/24", namespace=self.ns, status=self.status_active)

    def test_prefix_delete_when_delete_on_sync_false(self):
        """When delete_prefixes_on_sync is False, delete() does not append to objects_to_delete."""
        model = NautobotPrefix(prefix="10.99.0.0/24", namespace=self.ns.name, uuid=self.prefix.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 0)

    @patch("nautobot_ssot.integrations.aristacv.diffsync.models.nautobot.OrmPrefix.objects.get")
    def test_prefix_delete_when_delete_on_sync_true(self, mock_pf_get):
        """When delete_prefixes_on_sync is True, delete() appends prefix to objects_to_delete."""
        mock_pf_get.return_value = self.prefix
        self.adapter.job.app_config = get_config()._replace(delete_prefixes_on_sync=True)
        model = NautobotPrefix(prefix="10.99.0.0/24", namespace=self.ns.name, uuid=self.prefix.id)
        model.adapter = self.adapter
        model.delete()
        self.assertEqual(len(self.adapter.objects_to_delete["prefixes"]), 1)
        self.assertEqual(self.adapter.objects_to_delete["prefixes"][0].id, self.prefix.id)
