"""Tests for Bootstrap handling of empty or missing optional data (GitHub issue #748)."""

from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.choices import CustomFieldTypeChoices
from nautobot.extras.models import CustomField, Role, Status, Tag

from nautobot_ssot.integrations.bootstrap.constants import DEFAULT_COLOR
from nautobot_ssot.integrations.bootstrap.diffsync.adapters.bootstrap import BootstrapAdapter
from nautobot_ssot.integrations.bootstrap.diffsync.adapters.nautobot import NautobotAdapter
from nautobot_ssot.integrations.bootstrap.diffsync.models.nautobot import (
    NautobotLocation,
    NautobotRole,
    NautobotTag,
)


def _mock_job():
    """Return a minimal mocked Job usable by the Bootstrap adapters and models."""
    job = MagicMock()
    job.debug = False
    job.data_source = "Bootstrap"
    return job


class TestBootstrapAdapterEmptyData(TestCase):
    """Verify the Bootstrap adapter applies defaults when optional keys are missing or empty."""

    def setUp(self):
        """Create a Bootstrap adapter with no branch overrides."""
        self.adapter = BootstrapAdapter(job=_mock_job(), sync=None, client=MagicMock())
        self.adapter.branch_vars = {}

    def test_default_color_is_valid(self):
        """The fallback color must be 6 lowercase hex characters without a leading '#'."""
        self.assertRegex(DEFAULT_COLOR, r"^[0-9a-f]{6}$")

    def test_load_tag_without_color_key(self):
        """A Tag with no `color` key falls back to the default color."""
        self.adapter.load_tag({"name": "NoColorKey", "description": "", "content_types": ["dcim.device"]})
        self.assertEqual(self.adapter.get("tag", "NoColorKey").color, DEFAULT_COLOR)

    def test_load_tag_with_empty_color(self):
        """A Tag with a blank `color` value falls back to the default color."""
        self.adapter.load_tag({"name": "NullColor", "color": None, "description": "", "content_types": []})
        self.adapter.load_tag({"name": "EmptyColor", "color": "", "description": "", "content_types": []})
        self.assertEqual(self.adapter.get("tag", "NullColor").color, DEFAULT_COLOR)
        self.assertEqual(self.adapter.get("tag", "EmptyColor").color, DEFAULT_COLOR)

    def test_load_tag_with_color_keeps_color(self):
        """A Tag with an explicit `color` keeps it."""
        self.adapter.load_tag({"name": "Colored", "color": "795548", "description": "", "content_types": []})
        self.assertEqual(self.adapter.get("tag", "Colored").color, "795548")

    def test_load_role_without_color(self):
        """A Role with no or blank `color` falls back to the default color."""
        self.adapter.load_role({"name": "NoColorRole", "weight": None, "description": "", "content_types": []})
        self.adapter.load_role(
            {"name": "NullColorRole", "weight": None, "description": "", "color": None, "content_types": []}
        )
        self.assertEqual(self.adapter.get("role", "NoColorRole").color, DEFAULT_COLOR)
        self.assertEqual(self.adapter.get("role", "NullColorRole").color, DEFAULT_COLOR)

    def test_load_location_without_optional_keys(self):
        """A Location with only required keys (no `time_zone`, etc.) loads without raising KeyError."""
        self.adapter.load_location({"name": "Minimal", "location_type": "Site", "status": "Active"})
        location = self.adapter.get("location", {"name": "Minimal", "location_type": "Site"})
        self.assertEqual(location.time_zone, "")
        self.assertEqual(location.facility, "")
        self.assertIsNone(location.parent)
        self.assertIsNone(location.tenant)
        self.assertIsNone(location.asn)
        self.assertEqual(location.tags, [])

    def test_load_tenant_and_tenant_group_without_parent(self):
        """TenantGroup without `parent` and Tenant without `tenant_group` load with None."""
        self.adapter.load_tenant_group({"name": "NoParentGroup", "description": ""})
        self.adapter.load_tenant({"name": "NoGroupTenant", "description": "", "tags": []})
        self.assertIsNone(self.adapter.get("tenant_group", {"name": "NoParentGroup", "parent": None}).parent)
        self.assertIsNone(self.adapter.get("tenant", "NoGroupTenant").tenant_group)


class TestNautobotModelsEmptyData(TestCase):
    """Verify the Nautobot DiffSync models create valid objects when optional values are blank."""

    @classmethod
    def setUpTestData(cls):
        """Ensure the custom fields set by the Bootstrap models exist for the tested content types."""
        content_types = [ContentType.objects.get_for_model(model) for model in (Tag, Role, Location)]
        for key, field_type, label in (
            ("system_of_record", CustomFieldTypeChoices.TYPE_TEXT, "System of Record"),
            ("last_synced_from_sor", CustomFieldTypeChoices.TYPE_DATE, "Last sync from System of Record"),
        ):
            custom_field, _ = CustomField.objects.get_or_create(key=key, defaults={"type": field_type, "label": label})
            custom_field.content_types.add(*content_types)

        cls.location_type, _ = LocationType.objects.get_or_create(name="Site")
        cls.status, _ = Status.objects.get_or_create(name="Active")
        cls.status.content_types.add(ContentType.objects.get_for_model(Location))

    def setUp(self):
        """Create a Nautobot adapter with a mocked job."""
        self.adapter = NautobotAdapter(job=_mock_job(), sync=None)

    def test_tag_create_with_blank_color(self):
        """Creating a Tag with a blank color uses a valid default color."""
        NautobotTag.create(
            adapter=self.adapter,
            ids={"name": "BlankColorTag"},
            attrs={"color": "", "content_types": [], "description": "", "system_of_record": "Bootstrap"},
        )
        self.assertEqual(Tag.objects.get(name="BlankColorTag").color, DEFAULT_COLOR)

    def test_role_create_without_color(self):
        """Creating a Role with no color uses a valid default color."""
        NautobotRole.create(
            adapter=self.adapter,
            ids={"name": "NoColorRole"},
            attrs={
                "weight": None,
                "description": "",
                "color": None,
                "content_types": [],
                "system_of_record": "Bootstrap",
            },
        )
        self.assertEqual(Role.objects.get(name="NoColorRole").color, DEFAULT_COLOR)

    def test_location_create_without_time_zone(self):
        """A Location loaded from Bootstrap data with no `time_zone` key is created in Nautobot."""
        bs_adapter = BootstrapAdapter(job=_mock_job(), sync=None, client=MagicMock())
        bs_adapter.branch_vars = {}
        bs_adapter.load_location({"name": "NoTimeZone", "location_type": "Site", "status": "Active"})
        bs_location = bs_adapter.get("location", {"name": "NoTimeZone", "location_type": "Site"})

        NautobotLocation.create(
            adapter=self.adapter,
            ids=bs_location.get_identifiers(),
            attrs=bs_location.get_attrs(),
        )
        location = Location.objects.get(name="NoTimeZone")
        self.assertIsNone(location.time_zone)
        self.assertEqual(location.facility, "")
