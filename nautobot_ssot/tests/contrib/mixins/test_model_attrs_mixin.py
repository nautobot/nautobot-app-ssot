"""Tests for contrib.NautobotModel."""

from typing import List, Optional

from unittest import TestCase
#from nautobot.core.testing import TestCase
from nautobot.dcim.models import LocationType



from nautobot_ssot.contrib.mixins import ModelAttributeMethodsMixin

class LocationTypeModel(ModelAttributeMethodsMixin):

    _model = LocationType

    name: str
    description: Optional[str]


class TestGetTypeHintsMethod(TestCase):
    """"""

    def test_simple_get_type_hints(self):
        result = LocationTypeModel.get_type_hints()
        self.assertTrue(result["name"], "<class 'str'>")

    def test_get_from_cache(self):
        LocationTypeModel.get_type_hints()
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[1], 1)
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[0], 0)
        LocationTypeModel.get_type_hints()
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[1], 1)
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[0], 1)
        LocationTypeModel.get_type_hints(include_extras=False)
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[1], 2)
        self.assertEqual(LocationTypeModel.get_type_hints.cache_info()[0], 1)

