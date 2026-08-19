"""Unit tests for the shipped ServiceNow mappings.yaml and its `match` clause rules."""

from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.servicenow.diffsync.adapter_servicenow import ServiceNowDiffSync


def validate_mappings(mapping_data):
    """Check that every `match` clause in a set of mappings can actually be applied.

    Each of these mistakes would fail quietly in production: the clause would never narrow anything, and the
    ambiguity it was added to prevent would come back as a per-object sync failure.

    Raises:
        ValueError: If a `match` entry names no value source, refers to a reference key that is not resolved
            earlier in the same mapping list, or matches on a column the referenced model does not load.
    """
    fields_by_table = {
        entry["table"]: ServiceNowDiffSync.fields_for_mappings(entry["mappings"]) for entry in mapping_data.values()
    }
    for modelname, entry in mapping_data.items():
        resolved_keys = set()
        for mapping in entry["mappings"]:
            reference = mapping.get("reference", {})
            for match in reference.get("match", []):
                where = f"{modelname}.{mapping['field']} match on column `{match.get('column')}`"
                if not match.get("key") and not match.get("field"):
                    raise ValueError(f"{where} names neither a `key` nor a `field` to take its value from.")
                if match.get("key") and match["key"] not in resolved_keys:
                    raise ValueError(
                        f"{where} uses key `{match['key']}`, which is not resolved by an earlier "
                        f"mapping of `{modelname}`."
                    )
                referenced_fields = fields_by_table.get(reference["table"])
                if referenced_fields is not None and match["column"] not in referenced_fields:
                    raise ValueError(
                        f"{where} is not among the columns loaded from table `{reference['table']}`, "
                        "so no loaded record will ever carry it."
                    )
            if "key" in reference:
                resolved_keys.add(reference["key"])


class MappingsYamlTestCase(TestCase):
    """Test the shipped mappings.yaml itself against the `match` clause rules."""

    PRODUCT_MODEL_MAPPINGS = [
        {"field": "manufacturer_name", "reference": {"key": "manufacturer", "table": "core_company", "column": "name"}},
        {"field": "model_name", "column": "name"},
    ]
    MANUFACTURER_MAPPING = {
        "field": "manufacturer_name",
        "reference": {"key": "manufacturer", "table": "core_company", "column": "name"},
    }

    @classmethod
    def _mapping_data(cls, match, product_model_mappings=None, device_mappings=None):
        """Build a two-model mapping_data whose device.model_name reference carries `match`."""
        model_mapping = {
            "field": "model_name",
            "reference": {
                "key": "model_id",
                "table": "cmdb_hardware_product_model",
                "column": "name",
                "match": match,
            },
        }
        return {
            "product_model": {
                "table": "cmdb_hardware_product_model",
                "mappings": cls.PRODUCT_MODEL_MAPPINGS if product_model_mappings is None else product_model_mappings,
            },
            "device": {
                "table": "cmdb_ci_ip_switch",
                "mappings": ([cls.MANUFACTURER_MAPPING, model_mapping] if device_mappings is None else device_mappings),
            },
        }

    def test_device_model_reference_is_disambiguated_by_manufacturer(self):
        """`cmdb_hardware_product_model.name` is not unique across manufacturers, so `name` alone collides."""
        mapping_data = ServiceNowDiffSync.load_yaml_datafile("mappings.yaml")
        model_mapping = next(
            mapping for mapping in mapping_data["device"]["mappings"] if mapping["field"] == "model_name"
        )
        match_columns = [entry["column"] for entry in model_mapping["reference"].get("match", [])]
        self.assertIn("manufacturer", match_columns)

    def test_shipped_mappings_pass_validation(self):
        validate_mappings(ServiceNowDiffSync.load_yaml_datafile("mappings.yaml"))

    def test_match_entry_must_name_a_value_source(self):
        """A match entry with no `key` and no `field` can never be applied, so it silently does nothing."""
        with self.assertRaises(ValueError):
            validate_mappings(self._mapping_data([{"column": "manufacturer"}]))

    def test_match_key_must_be_resolved_earlier_in_the_mapping(self):
        """References resolve in order, so a `key` defined later is never available when it is needed."""
        model_mapping = {
            "field": "model_name",
            "reference": {
                "key": "model_id",
                "table": "cmdb_hardware_product_model",
                "column": "name",
                "match": [{"column": "manufacturer", "key": "manufacturer"}],
            },
        }
        with self.assertRaises(ValueError):
            validate_mappings(self._mapping_data(None, device_mappings=[model_mapping, self.MANUFACTURER_MAPPING]))

    def test_match_column_must_be_loaded_for_the_referenced_table(self):
        """A column the referenced model never loads is absent from every record, so it can never match."""
        with self.assertRaises(ValueError):
            validate_mappings(
                self._mapping_data(
                    [{"column": "manufacturer", "field": "manufacturer_name"}],
                    product_model_mappings=[{"field": "model_name", "column": "name"}],
                )
            )
