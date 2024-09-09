"""Tests for Bootstrap adapter."""

import json
from datetime import datetime
from unittest.mock import MagicMock

import yaml
from deepdiff import DeepDiff
from nautobot.core.testing import TransactionTestCase
from nautobot.extras.models import JobResult

from nautobot_ssot.integrations.bootstrap.diffsync.adapters.bootstrap import (
    BootstrapAdapter,
)
from nautobot_ssot.integrations.bootstrap.jobs import BootstrapDataSource

from .test_setup import (
    DEVELOP_YAML_SETTINGS,
    GLOBAL_JSON_SETTINGS,
    GLOBAL_YAML_SETTINGS,
    MODELS_TO_SYNC,
)


def load_yaml(path):
    """Load a yaml file."""
    with open(path, encoding="utf-8") as file:
        return yaml.safe_load(file.read())


def load_json(path):
    """Load a json file."""
    with open(path, encoding="utf-8") as file:
        return json.loads(file.read())


def assert_deep_diff(test_case, actual, expected, keys_to_normalize=None):
    # pylint: disable=duplicate-code
    """Custom DeepDiff assertion handling."""
    keys_to_normalize = keys_to_normalize or {}

    def normalize(item):  # pylint: disable=too-many-branches
        if isinstance(item, list):
            return [normalize(i) for i in item]
        if isinstance(item, dict):
            for key in list(item.keys()):
                if key in ["system_of_record", "model_flags", "uuid"]:
                    item.pop(key, None)
                elif key in keys_to_normalize and (item.get(key) is None or item.get(key) == ""):
                    item[key] = None
                if (
                    key
                    in [
                        "weight",
                        "parent",
                        "date_installed",
                        "asn",
                        "latitude",
                        "longitude",
                        "tenant",
                        "terminations",
                    ]
                    and item.get(key) is None
                ):
                    item.pop(key, None)
                if key == "parameters":
                    if "path" not in item[key]:
                        item[key]["path"] = None
                if key == "path" and item.get(key) is None:
                    item[key] = None
                if key == "content_types" or key == "provided_contents" and isinstance(item[key], list):
                    item[key] = sorted(["config contexts" if v == "extras.configcontext" else v for v in item[key]])
                if key == "date_allocated":
                    if item.get(key) is not None:
                        # Normalize the format to 'YYYY-MM-DD HH:MM:SS' for consistency
                        if isinstance(item[key], datetime):
                            item[key] = item[key].isoformat(sep=" ")
                        elif isinstance(item[key], str) and len(item[key]) == 10:
                            # Convert 'YYYY-MM-DD' format to 'YYYY-MM-DD 00:00:00'
                            item[key] += " 00:00:00"
                if key == "prefix":
                    # Sort prefixes based on network and namespace as unique identifiers
                    item[key] = sorted(item[key], key=lambda x: (x["network"], x["namespace"]))
            return {k: normalize(v) for k, v in item.items()}  # pylint: disable=duplicate-code
        return item

    actual_normalized = normalize(actual)
    expected_normalized = normalize(expected)

    diff = DeepDiff(
        actual_normalized,
        expected_normalized,
        ignore_order=True,
        ignore_string_type_changes=True,
        exclude_regex_paths=r"root\[\d+\]\['terminations'\]",
    )

    print("Actual Normalization", actual_normalized)
    print("Expected Normalization", expected_normalized)

    if diff:
        print("Differences found:")
        print(diff)

    test_case.assertEqual(diff, {})


class TestBootstrapAdapterTestCase(TransactionTestCase):
    """Test NautobotSsotBootstrapAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_diff = None

    def setUp(self):
        """Initialize test case."""
        self.job = BootstrapDataSource()
        self.job.job_result = JobResult.objects.create(
            name=self.job.class_path, task_name="fake task", worker="default"
        )

        self.bootstrap_client = MagicMock()
        self.bootstrap_client.get_global_settings.return_value = GLOBAL_YAML_SETTINGS
        self.bootstrap_client.get_develop_settings.return_value = DEVELOP_YAML_SETTINGS
        self.bootstrap_client.get_production_settings.return_value = GLOBAL_YAML_SETTINGS

        self.bootstrap = BootstrapAdapter(job=self.job, sync=None, client=self.bootstrap_client)

    def test_develop_settings(self):
        self.assertEqual(self.bootstrap_client.get_develop_settings(), DEVELOP_YAML_SETTINGS)

    def test_production_settings(self):
        self.assertEqual(self.bootstrap_client.get_production_settings(), GLOBAL_YAML_SETTINGS)

    def test_data_loading(self):
        """Test Nautobot Ssot Bootstrap load() function."""
        self.bootstrap.load()
        # self.maxDiff = None
        # pylint: disable=duplicate-code
        for key in MODELS_TO_SYNC:
            print(f"Checking: {key}")
            assert_deep_diff(
                self,
                list(self.bootstrap.dict().get(key, {}).values()),
                GLOBAL_JSON_SETTINGS.get(key, []),
                keys_to_normalize={
                    "parent",
                    "nestable",
                    "tenant",
                    "tenant_group",
                    "terminations",
                    "provider_network",
                    "upstream_speed_kbps",
                    "location",
                },
            )
