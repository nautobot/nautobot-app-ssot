"""Unit tests for the ServiceNow DiffSync model write path."""

import json
from base64 import b64decode
from collections import defaultdict
from copy import deepcopy
from unittest.mock import MagicMock

from diffsync.enum import DiffSyncStatus
from diffsync.exceptions import ObjectNotCreated, ObjectNotDeleted, ObjectNotUpdated
from nautobot.apps.testing import TestCase

from nautobot_ssot.integrations.servicenow.diffsync import models
from nautobot_ssot.integrations.servicenow.diffsync.adapter_servicenow import ServiceNowDiffSync
from nautobot_ssot.integrations.servicenow.exceptions import AmbiguousReferenceError, MissingReferenceError
from nautobot_ssot.integrations.servicenow.third_party.pysnow.exceptions import MultipleResults

MODELS_TABLE = "cmdb_hardware_product_model"
DEVICE_TABLE = "cmdb_ci_ip_switch"

CISCO_SYS_ID = "c0000000000000000000000000000001"
ACME_SYS_ID = "c0000000000000000000000000000002"
CISCO_MODEL_SYS_ID = "m0000000000000000000000000000001"
ACME_MODEL_SYS_ID = "m0000000000000000000000000000002"

MANUFACTURER_MATCH = [
    {
        "column": "manufacturer",
        "key": "manufacturer",
        "field": "manufacturer_name",
        "reference": {"table": "core_company", "column": "name"},
    }
]


def device_entry(match=None):
    """Build a `device` mapping entry, optionally disambiguating the model_name reference by `match`."""
    model_reference = {"key": "model_id", "table": "cmdb_hardware_product_model", "column": "name"}
    if match:
        model_reference["match"] = match
    return {
        "table": "cmdb_ci_ip_switch",
        "mappings": [
            {"field": "name", "column": "name"},
            {
                "field": "manufacturer_name",
                "reference": {"key": "manufacturer", "table": "core_company", "column": "name"},
            },
            {"field": "model_name", "reference": model_reference},
        ],
    }


def interface_entry():
    """Build an `interface` mapping entry, whose device_name is a reference to the device table."""
    return {
        "table": "cmdb_ci_network_adapter",
        "mappings": [
            {"field": "name", "column": "name"},
            {"field": "device_name", "reference": {"key": "cmdb_ci", "table": DEVICE_TABLE, "column": "name"}},
        ],
    }


def build_adapter(entry, sys_ids=None, candidates=None, result=None):
    """Build a ServiceNow adapter whose client returns `candidates` for every reference query.

    `result` is what the mocked ServiceNow resource returns from create/update/get.
    """
    resource = MagicMock()
    response = MagicMock()
    response.one.return_value = result if result is not None else {}
    resource.create.return_value = response
    resource.update.return_value = response
    resource.get.return_value = response
    client = MagicMock()
    client.get_all_by_query.return_value = list(candidates or [])
    client.resource.return_value = resource
    adapter = ServiceNowDiffSync(client=client, job=MagicMock())
    adapter.job.debug = False
    adapter.mapping_data = {"device": entry, "interface": interface_entry()}
    adapter.sys_ids = sys_ids or {}
    # objects_to_delete is a class attribute on the adapter, so shadow it to keep tests independent.
    adapter.objects_to_delete = defaultdict(list)
    return adapter


class ReferenceResolutionTestCase(TestCase):
    """Test that a reference either resolves to exactly one sys_id or raises."""

    def test_unresolvable_reference_raises_instead_of_writing_null(self):
        """A reference that matches nothing must not be silently written as a null column."""
        adapter = build_adapter(device_entry(), candidates=[])
        device = models.Device(name="switch1", adapter=adapter)
        with self.assertRaises(MissingReferenceError):
            device.map_data_to_sn_record(
                data={"name": "switch1", "model_name": "C9300-48P"},
                mapping_entry=adapter.mapping_data["device"],
            )

    def test_null_source_value_still_clears_the_reference(self):
        """A genuinely null value is an intentional clear, not a resolution failure."""
        adapter = build_adapter(device_entry())
        device = models.Device(name="switch1", adapter=adapter)
        record = device.map_data_to_sn_record(data={"model_name": None}, mapping_entry=adapter.mapping_data["device"])
        self.assertEqual(record, {"model_id": None})
        adapter.client.get_all_by_query.assert_not_called()

    def test_single_match_resolves(self):
        """A reference with no `match` clause and exactly one matching record still resolves."""
        adapter = build_adapter(device_entry(), candidates=[{"sys_id": CISCO_MODEL_SYS_ID, "name": "C9300-48P"}])
        device = models.Device(name="switch1", adapter=adapter)
        record = device.map_data_to_sn_record(
            data={"model_name": "C9300-48P"}, mapping_entry=adapter.mapping_data["device"]
        )
        self.assertEqual(record, {"model_id": CISCO_MODEL_SYS_ID})


class InMemoryReferenceResolutionTestCase(TestCase):
    """Test that references resolve from records already pulled at load time, without extra API calls."""

    def test_resolves_from_loaded_records_without_querying(self):
        """The load already fetched every candidate record; re-querying ServiceNow is wasted and ambiguous."""
        adapter = build_adapter(
            device_entry(),
            sys_ids={MODELS_TABLE: {CISCO_MODEL_SYS_ID: {"sys_id": CISCO_MODEL_SYS_ID, "name": "C9300-48P"}}},
        )
        device = models.Device(name="switch1", adapter=adapter)
        record = device.map_data_to_sn_record(
            data={"model_name": "C9300-48P"}, mapping_entry=adapter.mapping_data["device"]
        )
        self.assertEqual(record, {"model_id": CISCO_MODEL_SYS_ID})
        adapter.client.get_all_by_query.assert_not_called()

    def test_duplicate_loaded_records_raise_naming_every_candidate(self):
        """Ambiguity found in memory is reported directly; querying would only re-derive it."""
        adapter = build_adapter(
            device_entry(),
            sys_ids={
                MODELS_TABLE: {
                    CISCO_MODEL_SYS_ID: {
                        "sys_id": CISCO_MODEL_SYS_ID,
                        "name": "C9300-48P",
                        "manufacturer": CISCO_SYS_ID,
                    },
                    ACME_MODEL_SYS_ID: {
                        "sys_id": ACME_MODEL_SYS_ID,
                        "name": "C9300-48P",
                        "manufacturer": ACME_SYS_ID,
                    },
                }
            },
        )
        device = models.Device(name="switch1", adapter=adapter)
        with self.assertRaises(AmbiguousReferenceError) as context:
            device.map_data_to_sn_record(data={"model_name": "C9300-48P"}, mapping_entry=adapter.mapping_data["device"])
        self.assertEqual(sorted(context.exception.candidates), sorted([ACME_MODEL_SYS_ID, CISCO_MODEL_SYS_ID]))
        self.assertIn(CISCO_MODEL_SYS_ID, str(context.exception))
        adapter.client.get_all_by_query.assert_not_called()

    def test_api_fallback_registers_the_record_for_reuse(self):
        """A record resolved via the API joins the loaded set, so an identical lookup does not query again."""
        adapter = build_adapter(device_entry(), candidates=[{"sys_id": CISCO_MODEL_SYS_ID, "name": "C9300-48P"}])
        device = models.Device(name="switch1", adapter=adapter)
        for _ in range(2):
            device.map_data_to_sn_record(data={"model_name": "C9300-48P"}, mapping_entry=adapter.mapping_data["device"])
        self.assertEqual(adapter.client.get_all_by_query.call_count, 1)
        self.assertIn(CISCO_MODEL_SYS_ID, adapter.sys_ids[MODELS_TABLE])


class ReferenceMatchTestCase(TestCase):
    """Test that a `match` clause disambiguates a reference whose lookup column is not unique."""

    SYS_IDS = {
        "core_company": {
            CISCO_SYS_ID: {"sys_id": CISCO_SYS_ID, "name": "Cisco"},
            ACME_SYS_ID: {"sys_id": ACME_SYS_ID, "name": "Acme"},
        },
        MODELS_TABLE: {
            CISCO_MODEL_SYS_ID: {"sys_id": CISCO_MODEL_SYS_ID, "name": "C9300-48P", "manufacturer": CISCO_SYS_ID},
            ACME_MODEL_SYS_ID: {"sys_id": ACME_MODEL_SYS_ID, "name": "C9300-48P", "manufacturer": ACME_SYS_ID},
        },
    }

    def test_match_selects_the_model_belonging_to_the_manufacturer(self):
        """Two manufacturers sharing a model name collide on `name` alone; `manufacturer` separates them."""
        adapter = build_adapter(device_entry(MANUFACTURER_MATCH), sys_ids=deepcopy(self.SYS_IDS))
        device = models.Device(name="switch1", adapter=adapter)
        record = device.map_data_to_sn_record(
            data={"manufacturer_name": "Acme", "model_name": "C9300-48P"},
            mapping_entry=adapter.mapping_data["device"],
        )
        self.assertEqual(record, {"manufacturer": ACME_SYS_ID, "model_id": ACME_MODEL_SYS_ID})
        adapter.client.get_all_by_query.assert_not_called()

    def test_match_falls_back_to_context_when_the_sibling_key_is_not_being_written(self):
        """On update, `data` holds only the changed attribute, so the sibling sys_id is not in the payload."""
        adapter = build_adapter(device_entry(MANUFACTURER_MATCH), sys_ids=deepcopy(self.SYS_IDS))
        device = models.Device(name="switch1", adapter=adapter)
        record = device.map_data_to_sn_record(
            data={"model_name": "C9300-48P"},
            mapping_entry=adapter.mapping_data["device"],
            context={"manufacturer_name": "Cisco"},
        )
        self.assertEqual(record, {"model_id": CISCO_MODEL_SYS_ID})

    def test_ambiguity_report_names_the_field_it_could_not_narrow_by(self):
        """When the disambiguating value is unavailable, say so: that is the actionable part."""
        adapter = build_adapter(device_entry(MANUFACTURER_MATCH), sys_ids=deepcopy(self.SYS_IDS))
        device = models.Device(name="switch1", adapter=adapter)
        with self.assertRaises(AmbiguousReferenceError) as context:
            device.map_data_to_sn_record(data={"model_name": "C9300-48P"}, mapping_entry=adapter.mapping_data["device"])
        self.assertEqual(context.exception.unapplied, ["manufacturer_name"])
        self.assertIn("manufacturer_name", str(context.exception))

    def test_api_fallback_query_carries_every_match_column(self):
        """A store miss must query on the disambiguating columns too, not just the ambiguous one."""
        adapter = build_adapter(
            device_entry(MANUFACTURER_MATCH),
            sys_ids={"core_company": deepcopy(self.SYS_IDS["core_company"])},
            candidates=[{"sys_id": CISCO_MODEL_SYS_ID, "name": "C9300-48P", "manufacturer": CISCO_SYS_ID}],
        )
        device = models.Device(name="switch1", adapter=adapter)
        device.map_data_to_sn_record(
            data={"manufacturer_name": "Cisco", "model_name": "C9300-48P"},
            mapping_entry=adapter.mapping_data["device"],
        )
        self.assertEqual(
            adapter.client.get_all_by_query.call_args.args,
            (MODELS_TABLE, {"name": "C9300-48P", "manufacturer": CISCO_SYS_ID}),
        )


class CreateFailureTestCase(TestCase):
    """Test that an unresolvable reference fails the create rather than writing an incomplete record."""

    def test_unresolved_reference_fails_the_create_without_writing(self):
        """Writing the record anyway would leave the reference column unset while the sync reported success."""
        adapter = build_adapter(device_entry(), candidates=[])
        with self.assertRaises(ObjectNotCreated):
            models.Device.create(adapter, ids={"name": "switch1"}, attrs={"model_name": "C9300-48P"})
        adapter.client.resource.return_value.create.assert_not_called()

    def test_unresolved_reference_is_reported_and_recorded(self):
        """The user needs to know which record, field and value were skipped, and why."""
        adapter = build_adapter(device_entry(), candidates=[])
        with self.assertRaises(ObjectNotCreated):
            models.Device.create(adapter, ids={"name": "switch1"}, attrs={"model_name": "C9300-48P"})
        self.assertEqual(len(adapter.unresolved_references), 1)
        logged = str(adapter.job.logger.error.call_args)
        for expected in ("device", "switch1", "model_name", "C9300-48P", MODELS_TABLE):
            self.assertIn(expected, logged)


class UpdateFailureTestCase(TestCase):
    """Test that a failed update is reported as a failure, not as a silent no-op."""

    def _device(self, adapter, **attrs):
        return models.Device(name="switch1", adapter=adapter, sys_id="abc123", **attrs)

    def test_unresolved_reference_fails_the_update_without_writing(self):
        adapter = build_adapter(device_entry(), candidates=[])
        with self.assertRaises(ObjectNotUpdated):
            self._device(adapter).update({"model_name": "C9300-48P"})
        adapter.client.resource.return_value.update.assert_not_called()
        self.assertEqual(len(adapter.unresolved_references), 1)

    def test_ambiguous_update_query_fails_instead_of_returning_none(self):
        """Returning None left diffsync believing the update had succeeded."""
        adapter = build_adapter(device_entry())
        adapter.client.resource.return_value.update.side_effect = MultipleResults("got multiple")
        with self.assertRaises(ObjectNotUpdated):
            self._device(adapter).update({"asset_tag": "NEW-TAG"})

    def test_context_supplies_sibling_fields_absent_from_the_payload(self):
        """An update payload holds only the changed attribute, but the lookup still needs the manufacturer."""
        adapter = build_adapter(
            device_entry(MANUFACTURER_MATCH),
            sys_ids=deepcopy(ReferenceMatchTestCase.SYS_IDS),
            result={"sys_id": "abc123", "model_id": CISCO_MODEL_SYS_ID},
        )
        device = self._device(adapter, manufacturer_name="Cisco")
        device.update({"model_name": "C9300-48P"})
        payload = adapter.client.resource.return_value.update.call_args.kwargs["payload"]
        self.assertEqual(payload, {"model_id": CISCO_MODEL_SYS_ID})


class DeleteFailureTestCase(TestCase):
    """Test that a delete that cannot be targeted is reported as a failure."""

    def test_ambiguous_delete_query_raises_and_says_delete(self):
        adapter = build_adapter(device_entry())
        adapter.client.resource.return_value.get.return_value.one.side_effect = MultipleResults("got multiple")
        with self.assertRaises(ObjectNotDeleted):
            models.Device(name="switch1", adapter=adapter, sys_id="abc123").delete()
        self.assertIn("delete", str(adapter.job.logger.error.call_args).lower())
        self.assertNotIn("record to update", str(adapter.job.logger.error.call_args))

    def test_unresolved_reference_fails_the_delete(self):
        """A reference that will not resolve makes the delete query match the wrong records, or none."""
        adapter = build_adapter(device_entry(), candidates=[])
        interface = models.Interface(name="Ethernet1/1", device_name="switch1", adapter=adapter)
        with self.assertRaises(ObjectNotDeleted):
            interface.delete()
        self.assertEqual(adapter.objects_to_delete["interface"], [])
        self.assertEqual(len(adapter.unresolved_references), 1)


class CreateRegistrationTestCase(TestCase):
    """Test that a newly created record can be referenced by objects created later in the same run."""

    RESULT = {"sys_id": "new123", "name": "switch1"}

    def test_create_captures_the_new_sys_id(self):
        """The sys_id returned by ServiceNow was discarded, leaving the model unable to identify itself."""
        adapter = build_adapter(device_entry(), result=self.RESULT)
        model = models.Device.create(adapter, ids={"name": "switch1"}, attrs={})
        self.assertEqual(model.sys_id, "new123")
        self.assertIn("new123", adapter.sys_ids[DEVICE_TABLE])

    def test_interface_of_a_new_device_resolves_without_a_query(self):
        """A device created moments ago is in hand; its interfaces should not have to look it up."""
        adapter = build_adapter(device_entry(), result=self.RESULT)
        models.Device.create(adapter, ids={"name": "switch1"}, attrs={})
        interface = models.Interface(name="Ethernet1/1", device_name="switch1", adapter=adapter)
        record = interface.map_data_to_sn_record(
            data={"device_name": "switch1"}, mapping_entry=adapter.mapping_data["interface"]
        )
        self.assertEqual(record, {"cmdb_ci": "new123"})
        adapter.client.get_all_by_query.assert_not_called()


class BulkCreateInterfacesTestCase(TestCase):
    """Test that interfaces are not bulk-created against a device reference that did not resolve."""

    @staticmethod
    def _adapter(known_devices):
        """Adapter whose loaded set contains only `known_devices`; anything else fails to resolve."""
        adapter = build_adapter(
            device_entry(),
            sys_ids={DEVICE_TABLE: {f"sys-{name}": {"sys_id": f"sys-{name}", "name": name} for name in known_devices}},
            candidates=[],
        )
        batch_response = MagicMock()
        batch_response.status_code = 200
        batch_response.json.return_value = {"unserviced_requests": []}
        # bulk_create_interfaces reads the wrapped requests.Response off the pysnow response object.
        adapter.client.resource.return_value.request.return_value._response = batch_response  # pylint: disable=protected-access
        return adapter

    def _queue(self, adapter, device_name, *interface_names):
        adapter.interfaces_to_create_per_device[device_name] = [
            models.Interface(name=name, device_name=device_name, adapter=adapter) for name in interface_names
        ]
        return adapter.interfaces_to_create_per_device[device_name]

    def test_unresolvable_device_skips_the_batch_instead_of_creating_orphans(self):
        """Sending a null cmdb_ci would create interfaces attached to nothing."""
        adapter = self._adapter(known_devices=[])
        interfaces = self._queue(adapter, "switch1", "Ethernet1/1", "Ethernet1/2")
        adapter.bulk_create_interfaces()
        adapter.client.resource.return_value.request.assert_not_called()
        self.assertEqual(len(adapter.unresolved_references), 2)
        for interface in interfaces:
            self.assertEqual(interface.get_status()[0], DiffSyncStatus.FAILURE)

    def test_one_failing_device_does_not_stop_the_next(self):
        """A batch is per device; one device's bad reference must not cancel another device's interfaces."""
        adapter = self._adapter(known_devices=["switch2"])
        self._queue(adapter, "switch1", "Ethernet1/1")
        self._queue(adapter, "switch2", "Ethernet1/1")
        adapter.bulk_create_interfaces()
        request = adapter.client.resource.return_value.request
        self.assertEqual(request.call_count, 1)
        payload = json.loads(request.call_args.kwargs["data"])
        self.assertEqual(len(payload["rest_requests"]), 1)
        body = json.loads(b64decode(payload["rest_requests"][0]["body"]).decode("utf-8"))
        self.assertEqual(body["cmdb_ci"], "sys-switch2")


class SyncCompleteReportTestCase(TestCase):
    """Test that a run which skipped reference writes does not end up looking clean."""

    @staticmethod
    def _error():
        return MissingReferenceError(
            table=MODELS_TABLE,
            column="name",
            value="C9300-48P",
            modelname="device",
            unique_id="switch1",
            field="model_name",
        )

    def test_unresolved_references_are_summarized_and_attached(self):
        adapter = build_adapter(device_entry())
        adapter.unresolved_references = [self._error()]
        adapter.sync_complete(source=MagicMock(), diff=MagicMock())
        filename, contents = adapter.job.create_file.call_args.args
        self.assertEqual(filename, "unresolved_references.txt")
        self.assertIn("switch1", contents)
        self.assertIn("model_name", contents)
        self.assertIn("1 reference", str(adapter.job.logger.error.call_args))

    def test_clean_run_reports_nothing(self):
        adapter = build_adapter(device_entry())
        adapter.sync_complete(source=MagicMock(), diff=MagicMock())
        adapter.job.create_file.assert_not_called()
        adapter.job.logger.error.assert_not_called()

    def test_a_failure_to_attach_the_report_does_not_sink_the_sync(self):
        """Losing a whole sync to a report-file size limit would be absurd."""
        adapter = build_adapter(device_entry())
        adapter.unresolved_references = [self._error()]
        adapter.job.create_file.side_effect = ValueError("file too large")
        adapter.sync_complete(source=MagicMock(), diff=MagicMock())
        adapter.job.logger.warning.assert_called()
