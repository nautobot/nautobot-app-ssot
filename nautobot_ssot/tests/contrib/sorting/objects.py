"""Unit tests objects for use contrib sorting unittests."""

from typing import List, Optional

from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import Annotated, TypedDict

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel
from nautobot_ssot.contrib.typeddicts import SortKey
from nautobot.dcim.models import Device


class BasicTagDict(TypedDict):
    """Basic TypedDict without sort key."""

    name: str
    description: Optional[str]


class TagDict(TypedDict):
    """Many-to-many relationship typed dict explaining which fields are interesting."""

    name: Annotated[str, SortKey]
    description: Optional[str] = ""


class BasicNautobotTag(NautobotModel):
    """A tag model for use in testing."""

    _model = Tag
    _modelname = "tag"
    _identifiers = ("name",)
    _attributes = ("description",)

    name: str
    description: Optional[str] = None


class BasicNautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[BasicNautobotTag] = []


class NautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[TagDict] = []


class SimpleNautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[dict] = []


class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant",)
    tenant = NautobotTenant



##################################################################################
##################################################################################
##################################################################################


class SortableInterfaceDict(TypedDict):
    """TypedDict for interfaces with sort key specified."""

    name: Annotated[str, SortKey]
    description: Optional[str]


class BasicModuleBayDict(TypedDict):
    """TypedDict for module bays without sort key specified."""

    name: str
    description: Optional[str] = ""


class SortableModuleBayDict(TypedDict):
    """TypedDict for module bays with sort key specified."""

    name: Annotated[str, SortKey]
    description: Optional[str] = ""



class SimpleNautobotDevice(NautobotModel):
    """Device model with a basic one attribute set to a standard dictionary type."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "interfaces",
        "module_bays",
        "description",
    )

    name: str
    interfaces: List["SortableInterfaceDict"] = []
    module_bays: List[dict] = []
    description: Optional[str]


class BasicNautobotDevice(NautobotModel):
    """Device model with a basic one attribute set to a typed dict without sort key specified."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "interfaces",
        "module_bays",
        "description",
    )

    name: str
    interfaces: List["SortableInterfaceDict"] = []
    module_bays: List["BasicModuleBayDict"] = []
    description: Optional[str]



class SortableNautobotDevice(NautobotModel):
    """Device model with a basic two attributes set to typed dicts with sort keys."""

    _model = Device
    _modelname = "device"
    _identifiers = ("name",)
    _attributes = (
        "interfaces",
        "module_bays",
        "description",
    )

    name: str
    interfaces: List["SortableInterfaceDict"] = []
    module_bays: List["SortableModuleBayDict"] = []
    description: Optional[str]

class BaseTestAdapter(NautobotAdapter):
    """"""
    def load(self):
        """"""
        self.add(self.device(
            name="TEST-001",
            interfaces=[
                {
                    "name": "D",
                    "description": "risus auctor sed"
                },
                {
                    "name": "E",
                    "description": "lacinia nisi venenatis"
                },
                {
                    "name": "C",
                    "description": "tellus in sagittis"
                },
                {
                    "name": "B",
                    "description": "ut odio cras mi"
                },
                {
                    "name": "A",
                    "description": "vel nisl duis ac nibh"
                },
            ],
            module_bays=[
                {"name": "I", "description": ""},
                {"name": "J", "description": ""},
                {"name": "H", "description": ""},
                {"name": "G", "description": ""},
                {"name": "F", "description": ""},
            ],
            description="",
        ))
        self.add(self.device(
            name="TEST-002",
            interfaces=[
                {
                    "name": "C",
                    "description": "tellus in sagittis"
                },
                {
                    "name": "E",
                    "description": "lacinia nisi venenatis"
                },
                {
                    "name": "A",
                    "description": "vel nisl duis ac nibh"
                },
                {
                    "name": "B",
                    "description": "ut odio cras mi"
                },
                {
                    "name": "D",
                    "description": "risus auctor sed"
                },
            ],
            module_bays=[
                {"name": "I", "description": ""},
                {"name": "J", "description": ""},
                {"name": "H", "description": ""},
                {"name": "G", "description": ""},
                {"name": "F", "description": ""},
            ],
            description="",
        ))


class SimpleAdapter(BaseTestAdapter):
    """"""

    top_level = ["device"]

    device = SimpleNautobotDevice

    
class BasicAdapter(BaseTestAdapter):
    """"""

    top_level = ["device"]

    device = BasicNautobotDevice
   

class AdvancedAdapter(BaseTestAdapter):
    """"""

    top_level = ["device"]

    device = SortableNautobotDevice
