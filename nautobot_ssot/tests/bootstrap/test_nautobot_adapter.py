"""Testing that objects are properly loaded from Nautobot into Nautobot adapter."""

# test_nautobot_adapter.py

from datetime import datetime

from deepdiff import DeepDiff
from django.test import TransactionTestCase

from .test_setup import (
    GLOBAL_JSON_SETTINGS,
    MODELS_TO_SYNC,
    NautobotTestSetup,
)


def assert_nautobot_deep_diff(test_case, actual, expected, keys_to_normalize=None):
    # pylint: disable=duplicate-code
    """Custom DeepDiff assertion handling."""
    keys_to_normalize = keys_to_normalize or {}

    def normalize(item, key=None):
        if isinstance(item, list):
            if key == "vrf":
                return sorted(
                    [normalize(i, key) for i in item],
                    key=lambda x: (x.get("name", ""), x.get("namespace", "")),
                )
            return [normalize(i, key) for i in item]

        if isinstance(item, dict):
            for item_key in list(item.keys()):
                if item_key in ["system_of_record", "model_flags", "uuid"]:
                    item.pop(item_key, None)
                elif item_key in ["secrets_group"] and "secrets_group" not in item:
                    item[item_key] = None
                elif item_key in keys_to_normalize and (item.get(item_key) is None or item.get(item_key) == ""):
                    item[item_key] = None

                if (
                    item_key
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
                    and item.get(item_key) is None
                ):
                    item.pop(item_key, None)

                if item_key == "content_types" or item_key == "provided_contents" and isinstance(item[item_key], list):
                    item[item_key] = sorted(item[item_key])

                if item_key == "date_allocated" and not item.get(item_key):
                    item.pop(item_key, None)

                if item_key == "parameters" and "path" not in item:
                    item["path"] = None

                if isinstance(item.get(item_key), datetime):
                    item[item_key] = item[item_key].isoformat(sep=" ")

            return {k: normalize(v, k) for k, v in item.items()}
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


class TestNautobotAdapterTestCase(TransactionTestCase):
    """Test NautobotAdapter class."""

    databases = ("default", "job_logs")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # self.maxDiff = None

    def setUp(self):
        """Initialize test case."""
        super().setUp()
        self.setup = NautobotTestSetup()
        self.nb_adapter = self.setup.nb_adapter

    def test_data_loading(self):
        """Test SSoT Bootstrap Nautobot load() function."""
        self.nb_adapter.load()
        # self.maxDiff = None
        # pylint: disable=duplicate-code
        for key in MODELS_TO_SYNC:
            print(f"Checking: {key}")
            assert_nautobot_deep_diff(
                self,
                list(self.nb_adapter.dict().get(key, {}).values()),
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
