"""Test utilities."""

import json


def json_fixture(json_file_path):
    """Load a JSON fixture.

    Args:
        json_file_path (str): Absolute path to the JSON file.

    Returns:
        dict | list: Parsed JSON content.
    """
    with open(json_file_path, encoding="utf-8") as file:
        return json.load(file)
