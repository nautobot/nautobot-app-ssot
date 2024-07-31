"""Test bootstrap adapter."""

import json
import yaml
import os
from unittest.mock import MagicMock

from nautobot.extras.models import JobResult
from nautobot.core.testing import TransactionTestCase
from nautobot_ssot.integrations.bootstrap.diffsync.adapters.bootstrap import BootstrapAdapter
from nautobot_ssot.integrations.bootstrap.jobs import BootstrapDataSource


def load_yaml(path):
    """Load a yaml file."""
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file.read())


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


GLOBAL_JSON_SETTINGS = load_json("nautobot_ssot/tests/bootstrap/fixtures/global_settings.json")
GLOBAL_YAML_SETTINGS = load_yaml("nautobot_ssot/tests/bootstrap/fixtures/global_settings.yml")
DEVELOP_YAML_SETTINGS = load_yaml("nautobot_ssot/tests/bootstrap/fixtures/develop.yml")

print(os.curdir)


class TestBootstrapAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotBootstrapAdapter class."""

    databases = ("default", "job_logs")

    def setUp(self):
        """Initialize test case."""
        self.job = BootstrapDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )

        self.bootstrap_client = MagicMock()
        self.bootstrap_client.get_global_settings.return_value = GLOBAL_JSON_SETTINGS
        self.bootstrap_client.get_develop_settings.return_value = DEVELOP_YAML_SETTINGS
        self.bootstrap_client.get_production_settings.return_value = GLOBAL_YAML_SETTINGS

        self.bootstrap = BootstrapAdapter(job=self.job, sync=None, client=self.bootstrap_client)

    def test_global_settings(self):
        self.assertEqual(self.bootstrap_client.get_global_settings(), GLOBAL_JSON_SETTINGS)

    def test_develop_settings(self):
        self.assertEqual(self.bootstrap_client.get_develop_settings(), DEVELOP_YAML_SETTINGS)

    def test_production_settings(self):
        self.assertEqual(self.bootstrap_client.get_production_settings(), GLOBAL_YAML_SETTINGS)

    def test_data_loading(self):
        """Test Nautobot Ssot Bootstrap load() function."""
        self.bootstrap.load()
        self.maxDiff = None

        self.assertEqual(
            sorted(self.bootstrap.dict()["tenant_group"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["tenant_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["tenant"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["tenant"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["role"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["role"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["manufacturer"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["manufacturer"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["platform"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["platform"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["location_type"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["location_type"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["location"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["location"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["team"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["team"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["contact"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["contact"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["provider"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["provider"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["provider_network"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["provider_network"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["circuit_type"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["circuit_type"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["circuit"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["circuit"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["circuit_termination"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["circuit_termination"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["secret"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["secret"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["secrets_group"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["secrets_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["git_repository"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["git_repository"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["dynamic_group"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["dynamic_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["computed_field"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["computed_field"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["tag"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["tag"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["graph_ql_query"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["graph_ql_query"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["software"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["software"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["software_image"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["software_image"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["validated_software"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["validated_software"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["namespace"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["namespace"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["rir"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["rir"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["vlan_group"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["vlan_group"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["vlan"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["vlan"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["vrf"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["vrf"], key=lambda x: x[1]),
        )
        self.assertEqual(
            sorted(self.bootstrap.dict()["prefix"], key=lambda x: x[1]),
            sorted(GLOBAL_YAML_SETTINGS["prefix"], key=lambda x: x[1]),
        )
