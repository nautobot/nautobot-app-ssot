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
            # Sort all other lists by their string representation
            return sorted([normalize(i, key) for i in item], key=str)

        if isinstance(item, dict):
            # Create a new dict with sorted keys
            normalized_dict = {}
            for item_key in sorted(item.keys()):
                # Skip system fields
                if item_key in ["system_of_record", "model_flags", "uuid"]:
                    continue
                
                # Handle special cases for None values
                if item_key == "parent" and item.get(item_key) is None:
                    continue  # Skip parent field entirely when None
                elif item_key in ["secrets_group"] and "secrets_group" not in item:
                    normalized_dict[item_key] = None
                elif item_key in keys_to_normalize and (item.get(item_key) is None or item.get(item_key) == ""):
                    normalized_dict[item_key] = None
                # Handle other fields that should be skipped when None
                elif (
                    item_key in [
                        "weight",
                        "date_installed",
                        "asn",
                        "latitude",
                        "longitude",
                        "tenant",
                        "terminations",
                    ]
                    and item.get(item_key) is None
                ):
                    continue
                # Handle content types
                elif (
                    item_key == "content_types" or item_key == "provided_contents" and isinstance(item[item_key], list)
                ):
                    normalized_dict[item_key] = sorted(item[item_key])
                elif item_key == "date_allocated" and not item.get(item_key):
                    continue
                elif item_key == "parameters" and "path" not in item:
                    normalized_dict[item_key] = {"path": None, **item[item_key]}
                elif isinstance(item.get(item_key), datetime):
                    normalized_dict[item_key] = item[item_key].isoformat(sep=" ")
                else:
                    normalized_dict[item_key] = normalize(item[item_key], item_key)

            return normalized_dict
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
            models = list(self.nb_adapter.dict().get(key, {}).values())
            if key == "custom_field":
                for model in list(models):
                    if model["label"] in ["System of Record", "Last sync from System of Record"]:
                        models.remove(model)

            assert_nautobot_deep_diff(
                self,
                models,
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
