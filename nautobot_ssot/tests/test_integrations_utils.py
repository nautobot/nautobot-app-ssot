"""Tests for shared helpers used across `nautobot_ssot.integrations`."""

from datetime import datetime
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, override_settings
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.models import Status
from nautobot.extras.models.metadata import MetadataType, MetadataTypeDataTypeChoices, ObjectMetadata

from nautobot_ssot.integrations.metadata_utils import (
    add_or_update_metadata_on_object,
    object_has_metadata,
)
from nautobot_ssot.integrations.utils import (
    each_enabled_integration,
    each_enabled_integration_module,
)


@override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_aci": True, "enable_infoblox": True}})
class TestEachEnabledIntegration(TestCase):
    """Drives integration discovery from `enable_<name>` keys in PLUGINS_CONFIG."""

    def test_yields_only_integrations_with_enable_flag_set(self):
        """Only directory names whose `enable_<name>` config key is truthy are yielded.

        Directories without an explicit enable flag (or with one set to False) are filtered out,
        so this is what `ready()` consults when wiring up signals at app startup.
        """
        self.assertEqual(set(each_enabled_integration()), {"aci", "infoblox"})


class TestEachEnabledIntegrationModule(TestCase):
    """Drives per-integration submodule import, delegating discovery to `each_enabled_integration`."""

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_aci": True}})
    def test_yields_real_module_for_enabled_integration(self):
        """A submodule that exists for an enabled integration is returned as an imported module object."""
        modules = list(each_enabled_integration_module("constant"))
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].__name__, "nautobot_ssot.integrations.aci.constant")

    @override_settings(PLUGINS_CONFIG={"nautobot_ssot": {"enable_aci": True}})
    def test_silently_skips_missing_submodule(self):
        """A requested submodule that does not exist for an enabled integration is logged and skipped, not raised."""
        self.assertEqual(list(each_enabled_integration_module("module_that_does_not_exist")), [])


class TestObjectHasMetadata(TestCase):
    """Tests the read-only `object_has_metadata` predicate against a sample DCIM Location."""

    def setUp(self):
        """Create a Location to act as the object under test."""
        status = Status.objects.get(name="Active")
        location_type = LocationType.objects.create(name="mu-test-loc-type")
        self.location = Location.objects.create(name="mu-test-loc", location_type=location_type, status=status)

    def test_returns_false_when_no_metadata_attached(self):
        """With neither MetadataType nor ObjectMetadata present, the helper returns False rather than raising."""
        self.assertFalse(object_has_metadata(self.location, integration="MyIntegration"))

    def test_returns_true_when_metadata_attached(self):
        """Once a matching MetadataType + ObjectMetadata pair exists, the helper returns True."""
        metadata_type = MetadataType.objects.create(
            name="Last Sync from MyIntegration",
            data_type=MetadataTypeDataTypeChoices.TYPE_DATETIME,
        )
        metadata_type.content_types.add(ContentType.objects.get_for_model(Location))
        ObjectMetadata.objects.create(
            assigned_object=self.location,
            metadata_type=metadata_type,
            scoped_fields=["name"],
            value=datetime.now().isoformat(timespec="seconds"),
        )
        self.assertTrue(object_has_metadata(self.location, integration="MyIntegration"))


class TestAddOrUpdateMetadataOnObject(TestCase):
    """Tests the create-then-update behaviour of `add_or_update_metadata_on_object`."""

    def setUp(self):
        """Create a Location and a fake adapter exposing the `job.data_source`/`job.debug`/`job.logger` surface used by the helper."""
        status = Status.objects.get(name="Active")
        location_type = LocationType.objects.create(name="mu-add-loc-type")
        self.location = Location.objects.create(name="mu-add-loc", location_type=location_type, status=status)

        self.adapter = MagicMock()
        self.adapter.job.data_source = "TestIntegration"
        self.adapter.job.debug = False
        self.scoped_fields = {"dcim.location": ["name"]}

    def test_creates_metadata_on_first_call(self):
        """First invocation creates the MetadataType and returns an unsaved ObjectMetadata seeded with the scoped fields and a timestamp value."""
        metadata = add_or_update_metadata_on_object(self.adapter, self.location, self.scoped_fields)
        metadata.save()
        self.assertEqual(metadata.scoped_fields, ["name"])
        self.assertEqual(metadata.metadata_type.name, "Last Sync from TestIntegration")
        self.assertTrue(metadata.value)

    def test_updates_existing_metadata_on_second_call(self):
        """Second invocation reuses the persisted ObjectMetadata row and overwrites its scoped_fields and value rather than creating a duplicate."""
        first = add_or_update_metadata_on_object(self.adapter, self.location, self.scoped_fields)
        first.save()
        first_pk = first.pk

        second = add_or_update_metadata_on_object(
            self.adapter, self.location, {"dcim.location": ["name", "description"]}
        )
        second.save()

        self.assertEqual(first_pk, second.pk)
        self.assertEqual(second.scoped_fields, ["name", "description"])

    def test_logs_warning_when_model_type_missing_from_scoped_fields(self):
        """When the object's `app_label.model_name` is absent from `scoped_fields`, the adapter logger emits a warning and the returned metadata's `scoped_fields` is left empty.

        Only the helper's return-value contract is asserted here; persistence of an empty
        `scoped_fields` is rejected by the DB and is not part of the helper's responsibility.
        """
        metadata = add_or_update_metadata_on_object(self.adapter, self.location, scoped_fields={})
        self.assertEqual(metadata.scoped_fields, [])
        self.adapter.job.logger.warning.assert_called_once()
