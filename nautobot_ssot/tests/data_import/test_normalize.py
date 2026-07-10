"""Tests for the normalization layer (flatten + derived tables)."""

from django.test import SimpleTestCase

from nautobot_ssot.integrations.data_import.engine import normalize
from nautobot_ssot.integrations.data_import.engine.sources import parse_csv


class FlattenRecordTests(SimpleTestCase):
    """flatten_record behavior."""

    def test_flatten_nested_dicts(self):
        record = {"name": "rtr-1", "site": {"name": "DC1", "region": {"name": "Central"}}}
        flat = normalize.flatten_record(record)
        self.assertEqual(flat["name"], "rtr-1")
        self.assertEqual(flat["site.name"], "DC1")
        self.assertEqual(flat["site.region.name"], "Central")

    def test_lists_of_dicts_preserved(self):
        record = {"name": "rtr-1", "interfaces": [{"if_name": "Gi0/0"}, {"if_name": "Gi0/1"}]}
        flat = normalize.flatten_record(record)
        self.assertIsInstance(flat["interfaces"], list)
        self.assertEqual(len(flat["interfaces"]), 2)

    def test_depth_cap(self):
        record = {"a": {"b": {"c": {"d": {"e": 1}}}}}
        flat = normalize.flatten_record(record, max_depth=3)
        self.assertIn("a.b.c.d", flat)
        self.assertEqual(flat["a.b.c.d"], {"e": 1})


class BuildTablesTests(SimpleTestCase):
    """build_tables: root tables and expanded child tables."""

    DOCUMENT = {
        "sources": [{"id": "api", "type": "api"}],
        "tables": [
            {"id": "devices", "from": "api"},
            {"id": "devices.interfaces", "from": "api", "expand": "interfaces", "parent": "devices"},
        ],
        "outputs": [
            {
                "table": "devices",
                "to": "dcim.device",
                "identifiers": {"name": {"column": "hostname"}},
                "fields": {},
            }
        ],
    }
    RECORDS = [
        {
            "hostname": "rtr-1",
            "interfaces": [{"if_name": "Gi0/0", "status": "up"}, {"if_name": "Gi0/1", "status": "down"}],
        },
        {"hostname": "rtr-2", "interfaces": [{"if_name": "Gi0/0", "status": "up"}]},
        {"hostname": "rtr-3"},  # no interfaces key
    ]

    def test_root_and_derived_tables(self):
        tables = normalize.build_tables(self.DOCUMENT, {"api": self.RECORDS})
        self.assertEqual(len(tables["devices"]), 3)
        self.assertEqual(len(tables["devices.interfaces"]), 3)

    def test_parent_key_injected(self):
        tables = normalize.build_tables(self.DOCUMENT, {"api": self.RECORDS})
        child_rows = tables["devices.interfaces"]
        self.assertEqual(child_rows[0][normalize.PARENT_KEY_COLUMN], "rtr-1")
        self.assertEqual(child_rows[2][normalize.PARENT_KEY_COLUMN], "rtr-2")

    def test_table_preview_marks_expandable(self):
        tables = normalize.build_tables(self.DOCUMENT, {"api": self.RECORDS})
        preview = normalize.table_preview(tables["devices"])
        self.assertIn("interfaces", preview["expandable_columns"])
        self.assertEqual(preview["row_count"], 3)


class ParseCSVTests(SimpleTestCase):
    """CSV parsing."""

    def test_basic_csv(self):
        text = "name,site,status\nrtr-1,DC1,up\nrtr-2,DC2,down\n"
        records = parse_csv(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0], {"name": "rtr-1", "site": "DC1", "status": "up"})

    def test_semicolon_delimiter_sniffed(self):
        text = "name;site\nrtr-1;DC1\n"
        records = parse_csv(text)
        self.assertEqual(records[0]["site"], "DC1")

    def test_empty_rows_skipped(self):
        text = "name,site\nrtr-1,DC1\n,,\n\n"
        records = parse_csv(text)
        self.assertEqual(len(records), 1)
