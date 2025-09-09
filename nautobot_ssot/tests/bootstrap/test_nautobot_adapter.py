"""Testing that objects are properly loaded from Nautobot into Nautobot adapter."""

# test_nautobot_adapter.py
# pylint: disable=R0912

from datetime import datetime

import pytz
from deepdiff import DeepDiff
from django.test import TransactionTestCase

from .test_bootstrap_setup import (
    GLOBAL_JSON_SETTINGS,
    KEYS_TO_NORMALIZE,
    MODELS_TO_TEST,
    NautobotTestSetup,
)


def assert_nautobot_deep_diff(test_case, actual, expected, keys_to_normalize=None):
    # pylint: disable=duplicate-code
    """Custom DeepDiff assertion handling."""
    keys_to_normalize = keys_to_normalize or {}

    def handle_datetime(datetime_obj, item_key):
        """Handle datetime object normalization based on field type."""
        if item_key == "date_allocated":
            # For date_allocated, always return just the date
            return datetime_obj.strftime("%Y-%m-%d")
        if item_key == "start_time":
            # For start_time, preserve existing timezone or add UTC if none
            if datetime_obj.tzinfo is None:
                datetime_obj = datetime_obj.replace(tzinfo=pytz.UTC)
            # Use isoformat to preserve timezone info
            return datetime_obj.isoformat()
        # For all other datetime fields, ensure timezone and use T separator
        if datetime_obj.tzinfo is None:
            datetime_obj = datetime_obj.replace(tzinfo=pytz.UTC)
        return datetime_obj.isoformat()

    def handle_special_fields(item_key, item, normalized_dict, keys_to_normalize):
        """Handle special field cases."""
        # Skip system fields
        if item_key in ["system_of_record", "model_flags", "uuid"]:
            return True

        # Handle special cases for None values
        if item_key == "parent" and item.get(item_key) is None:
            return True  # Skip parent field entirely when None
        if item_key in ["secrets_group"] and "secrets_group" not in item:
            normalized_dict[item_key] = None
            return True
        if item_key in keys_to_normalize and (item.get(item_key) is None or item.get(item_key) == ""):
            normalized_dict[item_key] = None
            return True
        return False

    def handle_none_fields(item_key, item):
        """Handle fields that should be skipped when None."""
        skip_if_none = ["weight", "date_installed", "asn", "latitude", "longitude", "tenant", "terminations"]
        if item_key in skip_if_none and item.get(item_key) is None:
            return True
        return False

    def handle_list_fields(item_key, item, normalized_dict):
        """Handle list fields."""
        if item_key in ["content_types", "provided_contents"] and isinstance(item[item_key], list):
            normalized_dict[item_key] = sorted(item[item_key])
            return True
        return False

    def normalize(item, key=None):
        """Normalize an item for comparison."""
        if isinstance(item, list):
            if key == "vrf":
                return sorted(
                    [normalize(i, key) for i in item],
                    key=lambda x: (x.get("name", ""), x.get("namespace", "")),
                )
            # Sort all other lists by their string representation
            return sorted([normalize(i, key) for i in item], key=str)

        if not isinstance(item, dict):
            return item

        # Create a new dict with sorted keys
        normalized_dict = {}
        for item_key in sorted(item.keys()):
            # Handle special fields first
            if handle_special_fields(item_key, item, normalized_dict, keys_to_normalize):
                continue

            # Handle fields that should be skipped when None
            if handle_none_fields(item_key, item):
                continue

            # Handle list fields
            if handle_list_fields(item_key, item, normalized_dict):
                continue

            # Handle date_allocated
            if item_key == "date_allocated" and not item.get(item_key):
                continue

            # Handle parameters
            if item_key == "parameters" and "path" not in item:
                normalized_dict[item_key] = {"path": None, **item[item_key]}
                continue

            # Handle datetime objects
            if isinstance(item.get(item_key), datetime):
                normalized_dict[item_key] = handle_datetime(item[item_key], item_key)
                continue

            # Normalize string date/datetime fields to YYYY-MM-DD
            if item_key in ["date_allocated", "valid_since", "valid_until", "release_date", "eos_date"]:
                if isinstance(item.get(item_key), str):
                    normalized_dict[item_key] = item[item_key][:10]
                    continue

            # Handle all other cases
            normalized_dict[item_key] = normalize(item[item_key], item_key)

        return normalized_dict

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
        for key in MODELS_TO_TEST:
            print(f"Checking: {key}")
            models = list(self.nb_adapter.dict().get(key, {}).values())
            if key == "custom_field":
                for model in list(models):
                    if model["label"] in ["System of Record", "Last sync from System of Record", "LibreNMS Device ID"]:
                        models.remove(model)

            assert_nautobot_deep_diff(
                self,
                models,
                GLOBAL_JSON_SETTINGS.get(key, []),
                keys_to_normalize=KEYS_TO_NORMALIZE,
            )
