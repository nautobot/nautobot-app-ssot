"""Unit tests for network_importer sync status."""
import uuid
import copy
from django.test import TestCase, TransactionTestCase
from nautobot.extras.models import Status


from django.test.client import RequestFactory
from django.contrib.auth import get_user_model

from nautobot.dcim.models import Site, Interface

from nautobot_ssot.tests.mock.basic import data as example_data

from nautobot_ssot.jobs.example_mixin import NautobotLocal, DictionaryLocal

User = get_user_model()


class NautobotMixinModelTestCase(TransactionTestCase):
    """Test the Onboarding models."""

    fixtures = ["nautobot_dump.json"]

    def setUp(self):
        """Initialize the Database with some datas."""
        self.user = User.objects.create(username="admin", is_active=True, is_superuser=True)
        self.request = RequestFactory().request(SERVER_NAME="WebRequestContext")
        self.request.id = uuid.uuid4()
        self.request.user = self.user

    def test_site_created_from_fixture(self):
        """Verify that OnboardingDevice is auto-created."""
        onboarding_device = Site.objects.get(slug="ams01")
        self.assertIsNotNone(onboarding_device)

    def test_basic_create(self):
        nautobot_adapter = NautobotLocal(None, request=self.request)
        nautobot_adapter.load()

        local_example_data = copy.deepcopy(example_data)
        local_example_data["interface"]["ams01-edge-01__Ethernet5/1"] = {
            "device": "ams01-edge-01",
            "name": "Ethernet5/1",
            "description": "",
            "type": "10gbase-t",
            "mode": "access",
            "status": "active",
        }
        local_example_data["device"]["ams01-edge-01"]["interfaces"].append("ams01-edge-01__Ethernet5/1")

        network_adapter = DictionaryLocal(None, data=local_example_data)
        network_adapter.load()

        nautobot_adapter.sync_from(network_adapter)
        self.assertEqual(Interface.objects.filter(name="Ethernet5/1").count(), 1)

    def test_basic_update(self):
        nautobot_adapter = NautobotLocal(None, request=self.request)
        nautobot_adapter.load()
        local_example_data = copy.deepcopy(example_data)
        local_example_data["interface"]["ams01-edge-01__Ethernet1/1"]["description"] = "new description"

        network_adapter_from_data = DictionaryLocal(None, data=local_example_data)
        network_adapter_from_data.load_from_dict(local_example_data)
        nautobot_adapter.sync_from(network_adapter_from_data)
        self.assertEqual(Interface.objects.filter(description="new description")[0].description, "new description")

    def test_basic_delete(self):
        nautobot_adapter = NautobotLocal(None, request=self.request)
        nautobot_adapter.load()
        local_example_data = copy.deepcopy(example_data)
        del local_example_data["interface"]["ams01-edge-01__Ethernet1/1"]
        local_example_data["device"]["ams01-edge-01"]["interfaces"].remove("ams01-edge-01__Ethernet1/1")

        network_adapter_from_data = DictionaryLocal(None, data=local_example_data)
        network_adapter_from_data.load_from_dict(local_example_data)
        nautobot_adapter.sync_from(network_adapter_from_data)
        self.assertEqual(Interface.objects.filter(name="Ethernet1/1").count(), 2)

    def test_add_cf_field(self):
        pass

    def test_append_attribute(self):
        pass

    def test_pop_attribute(self):
        pass

    def test_null_attribute(self):
        pass

    def test_null_cf_field(self):
        pass

    def test_null_fk(self):
        pass

    def test_null_m2m(self):
        pass

    def test_append_m2m(self):
        pass

    def test_pop_m2m(self):
        pass