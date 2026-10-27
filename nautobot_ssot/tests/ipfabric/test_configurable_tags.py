"""Tests for the configurable Tags that mark what the IP Fabric sync wrote and set aside."""

import pathlib
from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.extras.models import Tag
from nautobot.ipam.models import RouteTarget

import nautobot_ssot.integrations.ipfabric as ipfabric_package
from nautobot_ssot.integrations.ipfabric import constants, jobs
from nautobot_ssot.integrations.ipfabric.utilities import nbutils


class TestTheTagNamesComeFromSettings(TestCase):
    """The Tag names are configurable, so none may be written into the code that applies them."""

    def test_the_defaults_are_the_names_the_integration_has_always_used(self):
        self.assertEqual(constants.SYNCED_TAG_NAME, "SSoT Synced from IPFabric")
        self.assertEqual(constants.SAFE_DELETE_TAG_NAME, "SSoT Safe Delete")

    def test_no_module_spells_a_tag_name_out(self):
        """A literal name would ignore the setting, and with Sync Tagged Only scope the wrong objects."""
        package = pathlib.Path(ipfabric_package.__file__).parent
        offenders = [
            str(path.relative_to(package))
            for path in package.rglob("*.py")
            if path.name != "constants.py"
            and any(
                name in path.read_text(encoding="utf-8") for name in ("SSoT Synced from IPFabric", "SSoT Safe Delete")
            )
        ]
        self.assertEqual(offenders, [])


class TestARenamedSyncedTag(TestCase):
    """Changing `ipfabric_synced_tag` without renaming the Tag leaves the old objects on the old Tag."""

    def setUp(self):
        # The integration's startup signal has already made the default Tag in the test database.
        self.default_tag, _ = Tag.objects.get_or_create(name=constants.DEFAULT_SYNCED_TAG_NAME)
        self.default_tag.content_types.add(ContentType.objects.get_for_model(RouteTarget))
        self.route_target = RouteTarget.objects.create(name="65000:1")

    def test_nothing_is_counted_while_the_default_name_is_configured(self):
        self.route_target.tags.add(self.default_tag)
        self.assertEqual(nbutils.objects_left_on_the_default_synced_tag(), 0)

    def test_objects_still_on_the_default_tag_are_counted_when_the_new_one_is_unused(self):
        self.route_target.tags.add(self.default_tag)
        with patch.object(nbutils, "SYNCED_TAG_NAME", "Lab IP Fabric"):
            self.assertEqual(nbutils.objects_left_on_the_default_synced_tag(), 1)

    def test_nothing_is_counted_once_the_configured_tag_is_in_use(self):
        self.route_target.tags.add(self.default_tag)
        new_tag = Tag.objects.create(name="Lab IP Fabric")
        new_tag.content_types.add(ContentType.objects.get_for_model(RouteTarget))
        RouteTarget.objects.create(name="65000:2").tags.add(new_tag)
        with patch.object(nbutils, "SYNCED_TAG_NAME", "Lab IP Fabric"):
            self.assertEqual(nbutils.objects_left_on_the_default_synced_tag(), 0)

    def test_the_job_warns_with_how_to_migrate(self):
        job = jobs.IpFabricDataSource()
        job.logger = MagicMock()
        with patch.object(nbutils, "objects_left_on_the_default_synced_tag", return_value=3):
            job.warn_if_the_synced_tag_was_renamed()
        message = job.logger.warning.call_args.args[0] % job.logger.warning.call_args.args[1:]
        self.assertIn("3 carry 'SSoT Synced from IPFabric'", message)
        self.assertIn("rename that Tag", message)

    def test_the_job_says_nothing_when_no_object_was_left_behind(self):
        job = jobs.IpFabricDataSource()
        job.logger = MagicMock()
        with patch.object(nbutils, "objects_left_on_the_default_synced_tag", return_value=0):
            job.warn_if_the_synced_tag_was_renamed()
        job.logger.warning.assert_not_called()
