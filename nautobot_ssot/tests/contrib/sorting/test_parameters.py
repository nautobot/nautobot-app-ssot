"""Unit tests for contrib sorting."""

from typing_extensions import List, Optional
from unittest.mock import MagicMock

from django.test import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import Annotated, TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.tests.contrib.sorting.objects import NautobotTenant

from nautobot_ssot.contrib.sorting.parameters import (
    SortListTypeStandard,
    SortListTypeWithDict,
    parameter_factory,
)

class TestSortListTypeStandard(TestCase):
    """"""

    def setUp(self):
        """"""
        self.sorter = SortListTypeStandard(name="Test Parameter")

    def test_sort_strings(self):
        """Test sorting Basic strings."""
        sorted_list = self.sorter(["X", "C", "M"])
        self.assertEqual(sorted_list[0], "C")
        self.assertEqual(sorted_list[1], "M")
        self.assertEqual(sorted_list[2], "X")

    def test_sort_integers(self):
        """Test sorting integers."""
        sorted_list = self.sorter([100, 5, 60])
        self.assertEqual(sorted_list[0], 5)
        self.assertEqual(sorted_list[1], 60)
        self.assertEqual(sorted_list[2], 100)


class TestSortListTypeWithDict(TestCase):
    """"""

    def setUp(self):
        """"""
        self.sorter = SortListTypeWithDict(name="tags", sort_key="name")


    def test_sorting_basic_dictionaries(self):
        """"""
        list_1 = [{"name": "X"},{"name": "C"},{"name": "M"}]
        sorted_list = self.sorter(list_1)
        self.assertEqual(sorted_list[0]["name"], "C", sorted_list)
        self.assertEqual(sorted_list[1]["name"], "M", sorted_list)
        self.assertEqual(sorted_list[2]["name"], "X", sorted_list)


class TestParameterFactory(TestCase):
    """"""

    def setUp(self):
        """"""
        self.model = NautobotTenant
        self.type_hints = get_type_hints(self.model, include_extras=True)


    def test_valid_list_of_dictionaries(self):
        """"""
        result = parameter_factory(
            "tags",
            self.type_hints["tags"],
        )
        self.assertTrue(isinstance(result, SortListTypeWithDict))
