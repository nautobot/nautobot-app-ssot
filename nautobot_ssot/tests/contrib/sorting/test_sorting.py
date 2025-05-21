"""Unittests for testing sorting functions."""
# pylint: disable=protected-access

from unittest import TestCase
from unittest.mock import MagicMock

from nautobot_ssot.contrib.sorting import (
    _get_sorting_class,
    _sort_adapter,
    _sort_diffsync_instance,
    sort_relationships,
)
from copy import deepcopy
from nautobot_ssot.contrib.sorting.parameters import SortListTypeWithDict
from nautobot_ssot.contrib.sorting.models import ModelSortingInterface

from nautobot_ssot.tests.contrib.sorting.objects import (
    SimpleNautobotDevice,
    SimpleAdapter,
    BasicNautobotDevice,
    BasicAdapter,
    SortableNautobotDevice,
    AdvancedAdapter,
    SortableInterfaceDict,
    BasicModuleBayDict,
    SortableModuleBayDict,
)

class BaseTestCase(TestCase):
    """Base functionality for sorting unit tests."""

    def setUp(self):
        """Set up test cases."""
        interfaces = [
            SortableInterfaceDict(name="E", description=""),
            SortableInterfaceDict(name="B", description=""),
            SortableInterfaceDict(name="A", description=""),
            SortableInterfaceDict(name="D", description=""),
            SortableInterfaceDict(name="C", description=""),
        ]

        module_bays = [
            {"name": "I", "description": ""},
            {"name": "J", "description": ""},
            {"name": "H", "description": ""},
            {"name": "G", "description": ""},
            {"name": "F", "description": ""},
        ]

        self.simple_model = SimpleNautobotDevice(
            name="SIMPLE-001",
            interfaces=interfaces,
            module_bays=module_bays,
            description="Simple Device",
        )
        self.basic_model = BasicNautobotDevice(
            name="BASIC-001",
            interfaces=interfaces,
            module_bays=[
                BasicModuleBayDict(name="I", description=""),
                BasicModuleBayDict(name="J", description=""),
                BasicModuleBayDict(name="H", description=""),
                BasicModuleBayDict(name="G", description=""),
                BasicModuleBayDict(name="F", description=""),
            ],
            description="Basic Device"
        )
        self.advanced_model = SortableNautobotDevice(
            name="SORT-001",
            interfaces=interfaces,
            module_bays=[
                SortableModuleBayDict(name="I", description=""),
                SortableModuleBayDict(name="J", description=""),
                SortableModuleBayDict(name="H", description=""),
                SortableModuleBayDict(name="G", description=""),
                SortableModuleBayDict(name="F", description=""),
            ],
            description="Sortable Device"
        )

        self.simple_adapter = SimpleAdapter(
            job=MagicMock(),
        )
        self.simple_adapter.load()
        self.simple_sorter = ModelSortingInterface(self.simple_adapter.device)

        self.basic_adapter = BasicAdapter(
            job=MagicMock(),
        )
        self.basic_adapter.load()
        self.basic_sorter = ModelSortingInterface(self.basic_adapter.device)

        self.advanced_adapter = AdvancedAdapter(
            job=MagicMock(),
        )
        self.advanced_adapter.load()
        self.advanced_sorter = ModelSortingInterface(self.advanced_adapter.device)



class TestSortDiffSyncInstance(BaseTestCase):

    def test_simple_sorting(self):
        """Ensure only one list is sorted in """
        sorted_model: SimpleNautobotDevice = _sort_diffsync_instance(
            diffsync_obj=self.simple_model,
            sortable_params=self.simple_sorter.sortable_parameters,
        )
        self.assertEqual(sorted_model.interfaces[0]["name"], "A")
        self.assertEqual(sorted_model.module_bays[0]["name"], "I")

    def test_basic_sorting(self):
        """Ensure only one list is sorted in """
        sorted_model: BasicNautobotDevice = _sort_diffsync_instance(
            diffsync_obj=self.basic_model,
            sortable_params=self.basic_sorter.sortable_parameters,
        )
        self.assertEqual(sorted_model.interfaces[0]["name"], "A")
        self.assertEqual(sorted_model.module_bays[0]["name"], "I")


    def test_advanced_sorting(self):
        """Ensure only one list is sorted in """
        sorted_model: SortableNautobotDevice = _sort_diffsync_instance(
            diffsync_obj=self.advanced_model,
            sortable_params=self.advanced_sorter.sortable_parameters,
        )
        self.assertEqual(sorted_model.interfaces[0]["name"], "A")
        self.assertEqual(sorted_model.module_bays[0]["name"], "F")


class TestAdapterSorting(BaseTestCase):
    """Test cases for sorting at the individual adapter level."""

    def test_sorting_simple_adapter(self):
        """Test simple adapter to ensure only one item is sorted."""
        _sort_adapter(
            self.simple_adapter,
            [self.simple_sorter]
        )
        devices = self.simple_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

    def test_sorting_basic_adapter(self):
        """Test basic adapter to ensure only one item is sorted."""
        _sort_adapter(
            self.basic_adapter,
            [self.basic_sorter]
        )
        devices = self.basic_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

    def test_sorting_advanced_adapter(self):
        """Test advanced adapter to ensure two items are sorted."""
        _sort_adapter(
            self.advanced_adapter,
            [self.advanced_sorter]
        )
        devices = self.advanced_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "F")
        self.assertEqual(devices[1].module_bays[0]["name"], "F")


class TestSortRelationships(BaseTestCase):
    """"""

    def setUp(self):
        """"""
        super().setUp()

        self.target_simple = deepcopy(self.simple_adapter)
        self.target_basic = deepcopy(self.basic_adapter)
        self.target_advanced = deepcopy(self.advanced_adapter)

    def test_simple_sorting(self):
        """Test sorting relationships function with simple."""
        sort_relationships(self.simple_adapter, self.target_simple)

        devices = self.simple_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

        devices = self.target_simple.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

    def test_basic_sorting(self):
        """Test sorting relationships function with basic."""
        sort_relationships(self.basic_adapter, self.target_basic)

        devices = self.basic_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

        devices = self.target_basic.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "I")
        self.assertEqual(devices[1].module_bays[0]["name"], "I")

    def test_advanced_sorting(self):
        """Test sorting relationships function with advanced."""
        sort_relationships(self.advanced_adapter, self.target_advanced)

        devices = self.advanced_adapter.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "F")
        self.assertEqual(devices[1].module_bays[0]["name"], "F")
        
        devices = self.target_advanced.get_all("device")
        self.assertEqual(devices[0].interfaces[0]["name"], "A")
        self.assertEqual(devices[1].interfaces[0]["name"], "A")
        self.assertEqual(devices[0].module_bays[0]["name"], "F")
        self.assertEqual(devices[1].module_bays[0]["name"], "F")


