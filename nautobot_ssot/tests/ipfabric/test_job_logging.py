"""Tests that what the sync reports reaches the Job Result log.

Nautobot writes `JobLogEntry` rows from a handler attached to the Celery task logger, which a Job's
own `self.logger` sits under. A logger obtained any other way reaches the worker's stdout and
nothing else, so a message sent through one is invisible to the operator reading the run.
"""

import importlib
import logging
import pkgutil
import unittest.mock

from django.contrib.contenttypes.models import ContentType
from nautobot.apps.testing import TestCase
from nautobot.dcim.models import Location, LocationType
from nautobot.extras.management import populate_status_choices
from nautobot.extras.models import Status
from nautobot.ipam.models import VLAN

from nautobot_ssot.integrations import ipfabric
from nautobot_ssot.integrations.ipfabric.constants import SAFE_DELETE_VLAN_STATUS
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache
from nautobot_ssot.tests.ipfabric.job_log import job_log_text, job_logger
from nautobot_ssot.tests.ipfabric.test_ipfabric_adapter import build_adapter


def ipfabric_modules():
    """Yield every module of the IP Fabric integration."""
    for info in pkgutil.walk_packages(ipfabric.__path__, prefix=ipfabric.__name__ + "."):
        yield importlib.import_module(info.name)


class TestNoModuleHoldsItsOwnLogger(TestCase):
    """A logger of a module's own is the shape of the defect, so no module keeps one."""

    def test_no_module_holds_a_logger_under_any_name(self):
        held = {
            f"{module.__name__}.{name}": value
            for module in ipfabric_modules()
            for name, value in vars(module).items()
            if isinstance(value, logging.Logger)
        }

        self.assertEqual(
            held,
            {},
            "A logger of a module's own does not reach the Job Result log. Report through the "
            f"job's logger instead, or take one as an argument: {held}",
        )


class TestWhatALoadReports(TestCase):
    """The messages themselves, read back from the logger the operator sees."""

    def test_a_duplicate_the_loader_skips_is_reported_to_the_job(self):
        logger = job_logger()

        build_adapter(logger=logger)

        self.assertIn("Not syncing VLAN", job_log_text(logger, "warning"))

    def test_the_job_logger_is_the_only_thing_the_adapter_reports_through(self):
        """Nothing falls back to a logger of the module's own, at any level.

        Every level, and the module level `logging.warning()` style as well as a `Logger` method,
        since a call on the `logging` module itself reports to the root logger and holds no
        attribute for the structural test above to find.
        """
        logger = job_logger()
        levels = ("debug", "info", "warning", "error", "critical")

        with unittest.mock.patch.multiple(
            logging.Logger, **{name: unittest.mock.DEFAULT for name in levels}
        ) as methods:
            with unittest.mock.patch.multiple(logging, **{name: unittest.mock.DEFAULT for name in levels}) as functions:
                build_adapter(logger=logger)
        stray = {
            name: call_list
            for source in (methods, functions)
            for name, mocked in source.items()
            if (call_list := mocked.call_args_list)
        }

        self.assertEqual(stray, {}, f"Reported through a logger other than the job's: {stray}")
        self.assertTrue(logger.warning.called, "The run reports nothing at all, so this proves little.")


class TestTheVolumeOfWhatIsReported(TestCase):
    """A job log entry is a database write, so a per object message is a per object write.

    What is reported for every object the sync touches has to be counted and summarised, or a
    teardown of a large estate spends its time writing a list nobody reads.
    """

    def setUp(self):
        populate_status_choices()
        job_scoped_cache.clear_all()
        self.addCleanup(job_scoped_cache.clear_all)
        self.active = Status.objects.get(name="Active")
        location_type, _ = LocationType.objects.get_or_create(name="volume-site")
        location_type.content_types.add(ContentType.objects.get_for_model(VLAN))
        self.location = Location.objects.create(name="volume-site1", location_type=location_type, status=self.active)
        self.adapter = NautobotDiffSync(
            job=unittest.mock.MagicMock(),
            sync=unittest.mock.MagicMock(),
            sync_ipfabric_tagged_only=False,
            location_filter=None,
        )

    def safe_delete_many(self, count):
        """Run `safe_delete` over `count` VLANs, as a teardown of that many would."""
        model = self.adapter.vlan
        for vid in range(1, count + 1):
            vlan = VLAN.objects.create(name=f"volume{vid}", vid=vid, status=self.active)
            vlan.locations.add(self.location)
            diff_model = model(
                name=vlan.name, vid=vlan.vid, location=self.location.name, status="Active", vlan_pk=vlan.pk
            )
            diff_model.adapter = self.adapter
            diff_model.safe_delete(vlan, SAFE_DELETE_VLAN_STATUS, self.adapter.safe_delete_tag)

    def reported_lines(self):
        """Report the tally and return how many lines it took, with their text."""
        self.adapter.report_safe_delete_tally()
        logger = self.adapter.job.logger
        return logger.warning.call_count, job_log_text(logger, "warning")

    def test_nothing_is_reported_while_the_objects_are_being_marked(self):
        """The summary comes once the sync is over, not as each object goes by."""
        self.safe_delete_many(12)

        self.assertFalse(
            self.adapter.job.logger.warning.called,
            job_log_text(self.adapter.job.logger, "warning"),
        )

    def test_the_count_is_reported_rather_than_an_object_each(self):
        self.safe_delete_many(12)

        lines, text = self.reported_lines()

        self.assertIn("12 VLAN objects", text)
        self.assertLess(lines, 12, f"One line per object is what this exists to prevent: {text}")

    def test_the_number_of_lines_does_not_grow_with_the_estate(self):
        """What makes it bounded: more objects is the same lines, carrying larger numbers."""
        self.safe_delete_many(12)
        twelve, _ = self.reported_lines()
        self.adapter.job.logger.warning.reset_mock()
        self.safe_delete_many(40)

        forty, text = self.reported_lines()

        self.assertEqual(forty, twelve, f"The report grew with the estate: {text}")
        self.assertIn("40 VLAN objects", text)
