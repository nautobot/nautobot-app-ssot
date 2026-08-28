"""Test IPFabric Jobs."""

from copy import deepcopy
from unittest import mock

from django.conf import settings
from django.urls import reverse
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.ipfabric import jobs, sync_scope
from nautobot_ssot.integrations.ipfabric.sync_scope import SYNCABLE_OBJECTS, SyncScope

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot", {})
BACKUP_CONFIG = deepcopy(CONFIG)


class IPFabricJobTest(TestCase):
    """Test the IPFabric job."""

    def test_metadata(self):
        """Verify correctness of the Job Meta attributes."""
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.name)
        self.assertEqual("IPFabric ⟹ Nautobot", jobs.IpFabricDataSource.Meta.name)
        self.assertEqual("IP Fabric", jobs.IpFabricDataSource.Meta.data_source)
        self.assertEqual("Sync data from IP Fabric into Nautobot.", jobs.IpFabricDataSource.Meta.description)

    def test_data_mapping(self):
        """Verify correctness of the data_mappings() API."""
        mappings = jobs.IpFabricDataSource.data_mappings()

        self.assertEqual("Device", mappings[0].source_name)
        self.assertIsNone(mappings[0].source_url)
        self.assertEqual("Device", mappings[0].target_name)
        self.assertEqual(reverse("dcim:device_list"), mappings[0].target_url)

        self.assertEqual("Location", mappings[1].source_name)
        self.assertIsNone(mappings[1].source_url)
        self.assertEqual("Location", mappings[1].target_name)
        self.assertEqual(reverse("dcim:location_list"), mappings[1].target_url)

        self.assertEqual("Interfaces", mappings[2].source_name)
        self.assertIsNone(mappings[2].source_url)
        self.assertEqual("Interfaces", mappings[2].target_name)
        self.assertEqual(reverse("dcim:interface_list"), mappings[2].target_url)

        self.assertEqual("IP Addresses", mappings[3].source_name)
        self.assertIsNone(mappings[3].source_url)
        self.assertEqual("IP Addresses", mappings[3].target_name)
        self.assertEqual(reverse("ipam:ipaddress_list"), mappings[3].target_url)

        self.assertEqual("VLANs", mappings[4].source_name)
        self.assertIsNone(mappings[4].source_url)
        self.assertEqual("VLANs", mappings[4].target_name)
        self.assertEqual(reverse("ipam:vlan_list"), mappings[4].target_url)

        self.assertEqual("Connectivity Matrix", mappings[5].source_name)
        self.assertIsNone(mappings[5].source_url)
        self.assertEqual("Cables", mappings[5].target_name)
        self.assertEqual(reverse("dcim:cable_list"), mappings[5].target_url)

    # @override_settings(
    #     PLUGINS_CONFIG={
    #         "nautobot_ssot": {
    #             "IPFABRIC_HOST": "https://ipfabric.networktocode.com",
    #             "IPFABRIC_API_TOKEN": "1234",
    #         }
    #     }
    # )
    # def test_config_information(self):
    #     """Verify the config_information() API."""
    #     CONFIG["ipfabric_host"] = "https://ipfabric.networktocode.com"
    #     config_information = jobs.IpFabricDataSource.config_information()
    #     self.assertContains(
    #         config_information,
    #         {
    #             "IP Fabric host": "https://ipfabric.networktocode.com",
    #         },
    #     )
    #     # CLEANUP
    #     CONFIG["ipfabric_host"] = BACKUP_CONFIG["ipfabric_host"]


class IPFabricJobFormTestCase(TestCase):
    """Test that the job form is built from the object type registry."""

    def test_get_vars_includes_a_field_per_selectable_object_type(self):
        """The checkboxes are generated, so a missing one means the registry never reached the form."""
        with mock.patch.object(jobs.IpFabricDataSource, "_init_ipf_client", return_value=None):
            got_vars = jobs.IpFabricDataSource._get_vars()  # pylint: disable=protected-access

        for syncable in SYNCABLE_OBJECTS:
            self.assertIn(syncable.field_name, got_vars)

    def test_bulk_write_mode_is_offered_and_defaults_off(self):
        """Trading validation and change logging for speed has to be a deliberate act."""
        with mock.patch.object(jobs.IpFabricDataSource, "_init_ipf_client", return_value=None):
            got_vars = jobs.IpFabricDataSource._get_vars()  # pylint: disable=protected-access

        self.assertIn("bulk_write_mode", got_vars)
        self.assertFalse(got_vars["bulk_write_mode"].field_attrs["initial"])
        self.assertIn("bulk_write_mode", jobs.IpFabricDataSource.Meta.field_order)

    def test_bulk_write_mode_says_what_it_gives_up(self):
        """An operator cannot weigh the trade from the label alone."""
        description = jobs.IpFabricDataSource.bulk_write_mode.field_attrs["help_text"]
        for expected in ("change log", "validation"):
            self.assertIn(expected, description)

    def test_get_vars_omits_an_administratively_disabled_object_type(self):
        """A disabled object type must be absent from the form, not merely unticked."""
        with (
            mock.patch.object(jobs.IpFabricDataSource, "_init_ipf_client", return_value=None),
            mock.patch.dict(sync_scope.CONFIG, {"ipfabric_disabled_sync_objects": ["vlans"]}, clear=False),
        ):
            got_vars = jobs.IpFabricDataSource._get_vars()  # pylint: disable=protected-access

        self.assertNotIn("sync_vlans", got_vars)
        self.assertIn("sync_interfaces", got_vars)

    def test_field_order_names_every_object_type(self):
        """A generated field missing from `field_order` would be appended out of place."""
        for syncable in SYNCABLE_OBJECTS:
            self.assertIn(syncable.field_name, jobs.IpFabricDataSource.Meta.field_order)

    def test_run_resolves_the_submitted_selection_into_a_scope(self):
        """`run` is where the form's booleans become the one scope both adapters read."""
        job = jobs.IpFabricDataSource()
        job.logger = mock.MagicMock()

        with mock.patch("nautobot_ssot.jobs.base.DataSource.run"):
            job.run(sync_interfaces=True, sync_cables=True, sync_vlans=False, dryrun=True)

        scope = job.kwargs["scope"]
        self.assertTrue(scope.cables)
        self.assertFalse(scope.vlans)


class IPFabricSyncDataTest(TestCase):
    """Test that `sync_data` threads its job options through to both adapters."""

    def _job(self, scope=None, **overrides):
        """Return a job instance with mocked client, sync and logger.

        `scope` names the object types selected on the form; the default is what the form itself
        would submit with nothing changed.
        """
        job = jobs.IpFabricDataSource()
        job.client = mock.MagicMock()
        job.sync = mock.MagicMock()
        job.logger = mock.MagicMock()
        job.kwargs = {
            "snapshot": "$last",
            "dryrun": True,
            "safe_delete_mode": True,
            "sync_ipfabric_tagged_only": True,
            "bulk_write_mode": False,
            "location_filter": None,
            "debug": False,
            "scope": SyncScope(scope) if scope is not None else SyncScope.from_job_kwargs({}),
            **overrides,
        }
        return job

    def _run(self, job):
        """Run `sync_data` with both adapters mocked out, returning the mocks."""
        with (
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.IPFabricDiffSync") as mock_source,
            mock.patch("nautobot_ssot.integrations.ipfabric.jobs.NautobotDiffSync") as mock_dest,
        ):
            job.sync_data()
        return mock_source, mock_dest

    def test_sync_data_passes_bulk_write_mode_to_the_nautobot_adapter(self):
        """The Nautobot adapter is the one that writes, so it is the one that has to know."""
        job = self._job(bulk_write_mode=True)
        _source, dest = self._run(job)
        self.assertTrue(dest.call_args.kwargs["bulk_write_mode"])

    def test_sync_data_defaults_bulk_write_mode_off(self):
        job = self._job()
        _source, dest = self._run(job)
        self.assertFalse(dest.call_args.kwargs["bulk_write_mode"])

    def test_sync_data_passes_the_same_scope_to_both_adapters(self):
        """Both adapters must be given one scope object, or they can disagree about what is in scope."""
        job = self._job(scope=("interfaces", "cables"))

        mock_source, mock_dest = self._run(job)

        scope = mock_source.call_args.kwargs["scope"]
        self.assertIs(scope, mock_dest.call_args.kwargs["scope"])
        self.assertTrue(scope.cables)

    def test_sync_data_defaults_cables_off(self):
        """With the option unset, neither adapter loads Cables."""
        job = self._job()

        mock_source, mock_dest = self._run(job)

        self.assertFalse(mock_source.call_args.kwargs["scope"].cables)
        self.assertFalse(mock_dest.call_args.kwargs["scope"].cables)

    def test_sync_data_logs_the_resolved_scope(self):
        """The operator needs the log to say what was actually in scope, not what was submitted."""
        job = self._job(scope=("cables",))

        self._run(job)

        logged = " ".join(str(call) for call in job.logger.info.call_args_list)
        self.assertIn("cables: False", logged)
        self.assertTrue(
            any("requires 'interfaces'" in str(call) for call in job.logger.warning.call_args_list),
            f"Expected a warning naming the unmet requirement, got: {job.logger.warning.call_args_list}",
        )

    def test_sync_data_errors_without_a_client(self):
        """No client means the job reports and returns rather than proceeding."""
        job = self._job()
        job.client = None

        with mock.patch.object(jobs.IpFabricDataSource, "_init_ipf_client", return_value=None):
            job.sync_data()

        job.logger.error.assert_called_once()
