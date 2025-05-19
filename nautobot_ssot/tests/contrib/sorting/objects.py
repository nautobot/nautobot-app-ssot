"""Unit tests for contrib sorting."""

from typing import List, Optional
from unittest.mock import MagicMock

from django.test import TestCase
from nautobot.extras.models import Tag
from nautobot.tenancy.models import Tenant
from typing_extensions import Annotated, TypedDict, get_type_hints

from nautobot_ssot.contrib import NautobotAdapter, NautobotModel

from nautobot_ssot.contrib.typeddicts import SortKey


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


class NautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[TagDict] = []

class NautobotTenant(NautobotModel):
    """A basic tenant model for testing the `NautobotModel` base class."""

    _model = Tenant
    _modelname = "tenant"
    _identifiers = ("name",)
    _attributes = ("tags",)

    name: str
    tags: List[TagDict] = []


class TestAdapter(NautobotAdapter):
    """An adapter for testing the `BaseAdapter` base class."""

    top_level = ("tenant",)
    tenant = NautobotTenant
