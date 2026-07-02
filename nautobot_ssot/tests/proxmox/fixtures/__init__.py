"""Fixtures for Proxmox VE integration tests."""

import json
import os

real_path = os.path.dirname(os.path.realpath(__file__))


def json_fixture(filename):
    """Load a JSON fixture by file name relative to this directory."""
    with open(os.path.join(real_path, filename), encoding="utf-8") as handle:
        return json.load(handle)
