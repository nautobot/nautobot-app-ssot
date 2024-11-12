"""Unit tests for Nautobot IPAM model CRUD functions."""

from unittest.mock import patch

from diffsync import Adapter
from django.contrib.contenttypes.models import ContentType
from django.test import override_settings
from nautobot.core.testing import TransactionTestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status
from nautobot.ipam.models import Namespace, Prefix
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.meraki.diffsync.models.nautobot import NautobotPrefix


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_meraki": True}})
class TestNautobotPrefix(TransactionTestCase):  # pylint: disable=too-many-instance-attributes
    """Test the NautobotPrefix class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Configure common variables and objects for tests."""
        super().setUp()
        self.status_active = Status.objects.get(name="Active")
        site_lt = LocationType.objects.get_or_create(name="Site")[0]
        site_lt.content_types.add(ContentType.objects.get_for_model(Prefix))
        self.test_site = Location.objects.get_or_create(name="Test", location_type=site_lt, status=self.status_active)[
            0
        ]
        self.update_site = Location.objects.get_or_create(
            name="Update", location_type=site_lt, status=self.status_active
        )[0]
        self.test_tenant = Tenant.objects.get_or_create(name="Test")[0]
        self.update_tenant = Tenant.objects.get_or_create(name="Update")[0]
        self.test_ns = Namespace.objects.get_or_create(name="Test")[0]
        self.prefix = Prefix.objects.create(
            prefix="10.0.0.0/24", namespace=self.test_ns, status=self.status_active, tenant=self.test_tenant
        )
        self.adapter = Adapter()
        self.adapter.namespace_map = {"Test": self.test_ns.id, "Update": self.update_site.id}
        self.adapter.site_map = {"Test": self.test_site, "Update": self.update_site}
        self.adapter.tenant_map = {"Test": self.test_tenant.id, "Update": self.update_tenant.id}
        self.adapter.status_map = {"Active": self.status_active.id}
        self.adapter.prefix_map = {}
        self.adapter.objects_to_create = {"prefixes": []}
        self.adapter.objects_to_delete = {"prefixes": []}

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
