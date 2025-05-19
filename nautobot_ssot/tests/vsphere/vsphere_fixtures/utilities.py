"""Test Utils."""

import json


def json_fixture(json_file_path):
    """Load and return JSON Fixture."""
    with open(json_file_path, "r", encoding="utf-8") as file:
        return json.load(file)
