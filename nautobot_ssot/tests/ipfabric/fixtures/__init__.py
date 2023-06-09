"""Fixtures.

In your test file, simply import:
```
from nautobot_ssot_ipfabric.utilities import json_fixture
from nautobot_ssot_ipfabric.tests.fixtures import real_path
```
Then you can simply load fixtures that you have added to the fixtures directory
and assign them to your mocks by using the json_fixture utility:

json_fixture(f"{FIXTURES}/get_projects.json")

This will return a loaded json object.
"""
import os

real_path = os.path.dirname(os.path.realpath(__file__))
