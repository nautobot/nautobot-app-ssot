"""Test utilities."""

import json


def json_fixture(json_file_path):
    """Load and return a JSON fixture from a full path."""
    with open(json_file_path, encoding="utf-8") as file:
        return json.load(file)
