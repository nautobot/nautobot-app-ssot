#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
"""IP Fabric Data Target Job."""

import logging
import uuid

from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectNotCreated
from django.templatetags.static import static
from django.urls import reverse
from ipfabric import IPFClient
from nautobot.core.forms import DynamicModelChoiceField
from nautobot.dcim.models import Location
from nautobot.extras.jobs import BooleanVar, ChoiceVar, ScriptVariable
from nautobot.ipam.models import Namespace
from nautobot.tenancy.models import Tenant

from nautobot_ssot.integrations.ipfabric import constants, strict_mode
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.sync_scope import (
    SyncScope,
    disabled_keys,
    form_fields,
    scope_field_order,
)
from nautobot_ssot.integrations.ipfabric.utilities import nbutils
from nautobot_ssot.integrations.ipfabric.utilities.utils import job_scoped_cache
from nautobot_ssot.jobs.base import DataMapping, DataSource

LAST = "$last"
PREV = "$prev"
LAST_LOCKED = "$lastLocked"

name = "SSoT - IPFabric"  # pylint: disable=invalid-name


def is_valid_uuid(identifier):
    """Return true if the identifier it's a valid UUID."""
    try:
        uuid.UUID(str(identifier))
        return True
    except ValueError:
        return False


def get_formatted_snapshots(client: IPFClient):
    """Get all loaded snapshots and format them for display in choice menu.

    Returns:
        dict: Snapshot objects as dict of tuples {snapshot_ref: (description, snapshot_id)}
    """
    formatted_snapshots = {}
    snapshot_refs = []
    if client:
        for snapshot_ref, snapshot in client.loaded_snapshots.items():
            description = ""
            if snapshot_ref in [LAST, PREV, LAST_LOCKED]:
                description += f"{snapshot_ref}: "
                snapshot_refs.append(snapshot_ref)
            if snapshot.name:
                description += snapshot.name + " - " + snapshot.end.strftime("%d-%b-%y %H:%M:%S")
            else:
                description += snapshot.end.strftime("%d-%b-%y %H:%M:%S") + " - " + snapshot.snapshot_id
            formatted_snapshots[snapshot_ref] = (description, snapshot.snapshot_id)
        for ref in snapshot_refs:
            formatted_snapshots.pop(formatted_snapshots[ref][1], None)

    return formatted_snapshots


class OptionalObjectVar(ScriptVariable):
    """Custom implementation of an Optional ObjectVar.

    An object primary key is returned and accessible in job kwargs.
    """

    kwargs = {}
    form_field = DynamicModelChoiceField

    def __init__(
        self,
        model=None,
        display_field="display",
        query_params=None,
        null_option=None,
        *args,
        **kwargs,
    ):
        """Init."""
        super().__init__(*args, **kwargs)

        if model is not None:
            self.field_attrs["queryset"] = model.objects.all()
        else:
            raise TypeError("ObjectVar must specify a model")

        self.field_attrs.update(
            {
                "display_field": display_field,
                "query_params": query_params,
                "null_option": null_option,
            }
        )


# pylint:disable=too-few-public-methods
class IpFabricDataSource(DataSource):
    """Job syncing data from IP Fabric to Nautobot."""

    client = None
    snapshot = None
    debug = BooleanVar(description="Enable for more verbose debug logging")
    safe_delete_mode = BooleanVar(
        description="Records are not deleted. Status fields are updated as necessary.",
        default=True,
        label="Safe Delete Mode",
    )
    sync_ipfabric_tagged_only = BooleanVar(
        default=True,
        label="Sync Tagged Only",
        description=f"Only sync objects that have the '{constants.SYNCED_TAG_NAME}' Tag.",
    )
    bulk_write_mode = BooleanVar(
        default=False,
        label="Bulk Write Mode",
        description=(
            "Write Interfaces and IP Addresses in batches. Much faster on a large sync, at the cost "
            "of no change log entries, no signals and no per-object validation for those two. "
            "Database constraints still apply. Leave off unless a sync is too slow without it."
        ),
    )
    location_filter = OptionalObjectVar(
        description="Only sync Nautobot records belonging to a single Location.",
        model=Location,
        required=False,
    )
    tenant = OptionalObjectVar(
        description=(
            "The Tenant this IP Fabric instance belongs to. Only that Tenant's Nautobot records are "
            "read, and the records the sync creates are given it."
        ),
        model=Tenant,
        required=False,
    )
    namespace = OptionalObjectVar(
        description=(
            "The Namespace the sync's IP Addresses, Prefixes and VRFs belong to. Only that Namespace's "
            "records are read, and the records the sync creates are put in it. Global when left empty."
        ),
        model=Namespace,
        required=False,
    )
    kwargs = {}

    class Meta:
        """Metadata about this Job."""

        name = "IPFabric ⟹ Nautobot"
        data_source = "IP Fabric"
        data_source_icon = static("nautobot_ssot_ipfabric/ipfabric.png")
        description = "Sync data from IP Fabric into Nautobot."
        field_order = (
            "debug",
            "snapshot",
            "safe_delete_mode",
            "sync_ipfabric_tagged_only",
            "tenant",
            "namespace",
            "bulk_write_mode",
            strict_mode.FIELD_NAME,
            *scope_field_order(),
            "dryrun",
        )

    @staticmethod
    def _init_ipf_client():
        """Return `(client, None)`, or `(None, reason)` when no client can be built.

        The reason is returned rather than logged because the Job form builds a client too, before
        there is a run to log to. The SDK raises `RuntimeError` when its major version does not
        match the server's, and an `OSError` subclass for connection and HTTP failures.
        """
        try:
            client = IPFClient(
                base_url=constants.IPFABRIC_HOST,
                auth=constants.IPFABRIC_API_TOKEN,
                verify=constants.IPFABRIC_SSL_VERIFY,
                timeout=constants.IPFABRIC_TIMEOUT,
                unloaded=False,
            )
        except (RuntimeError, OSError) as error:
            return None, str(error)
        return client, None

    @classmethod
    def _get_vars(cls):
        """Extend JobDataSource._get_vars to include some variables.

        This also initializes them.
        """
        got_vars = super()._get_vars()

        if cls.client is None:
            cls.client, error = cls._init_ipf_client()
        else:
            try:
                cls.client.update()
            except (RuntimeError, OSError) as refresh_error:
                # Dropped rather than kept, so that the next form builds a new client instead of
                # failing on this one until the worker restarts.
                cls.client, error = None, str(refresh_error)
        if cls.client is None:
            # Building the form is not a run, so there is no Job Result log to report to and the
            # server log is the only place this can go. Fetched here rather than held by the
            # module, so that no code a run executes can report through it by mistake.
            logging.getLogger("nautobot.ssot.ipfabric").error(
                "IP Fabric client is not ready, so the Job form lists no snapshots: %s", error
            )

        formatted_snapshots = get_formatted_snapshots(cls.client)
        if formatted_snapshots:
            default_choice = formatted_snapshots["$last"][::-1]
        else:
            default_choice = "$last"

        cls.snapshot = ChoiceVar(
            description="IPFabric snapshot to sync from. Defaults to $last",
            default=default_choice,
            choices=[(snapshot_id, snapshot_name) for snapshot_name, snapshot_id in formatted_snapshots.values()],
            required=False,
        )

        if hasattr(cls, "snapshot"):
            got_vars["snapshot"] = cls.snapshot

        # Built here rather than declared on the class so that an object type an administrator has
        # disabled is absent from the form, not merely defaulted off.
        got_vars.update(form_fields())
        got_vars[strict_mode.FIELD_NAME] = strict_mode.form_field()

        return got_vars

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Device", None, "Device", reverse("dcim:device_list")),
            DataMapping("Device OS Version", None, "Software Version", reverse("dcim:softwareversion_list")),
            DataMapping("Device Image", None, "Software Image File", reverse("dcim:softwareimagefile_list")),
            DataMapping("Location", None, "Location", reverse("dcim:location_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
            DataMapping("Managed IP Summary", None, "Prefixes", reverse("ipam:prefix_list")),
            DataMapping("VLANs", None, "VLANs", reverse("ipam:vlan_list")),
            DataMapping("Stack Members", None, "Virtual Chassis", reverse("dcim:virtualchassis_list")),
            DataMapping("Connectivity Matrix", None, "Cables", reverse("dcim:cable_list")),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "IP Fabric Host": constants.IPFABRIC_HOST,
            "IP Fabric Timeout": str(constants.IPFABRIC_TIMEOUT),
            "Nautobot Host URL": constants.NAUTOBOT_HOST,
            "Default Device Role": constants.DEFAULT_DEVICE_ROLE,
            "Default Device Role Color": constants.DEFAULT_DEVICE_ROLE_COLOR,
            "Sync Device Type to Device Role": str(constants.SYNC_IPF_DEV_TYPE_TO_ROLE),
            "Default Device Status": constants.DEFAULT_DEVICE_STATUS,
            "Default Device Status Color": constants.DEFAULT_DEVICE_STATUS_COLOR,
            "Default Interface Type": constants.DEFAULT_INTERFACE_TYPE,
            "Use Canonical Interface Names": str(constants.IP_FABRIC_USE_CANONICAL_INTERFACE_NAME),
            "Default MAC Address": constants.DEFAULT_INTERFACE_MAC,
            "Default MTU": constants.DEFAULT_INTERFACE_MTU,
            "Default Cable Status": constants.DEFAULT_CABLE_STATUS,
            "Safe Delete Device Status": constants.SAFE_DELETE_DEVICE_STATUS,
            "Safe Delete Location Status": constants.SAFE_DELETE_LOCATION_STATUS,
            "Safe Delete IPAddress Status": constants.SAFE_DELETE_IPADDRESS_STATUS,
            "Safe Delete VLAN status": constants.SAFE_DELETE_VLAN_STATUS,
            "Safe Delete Cable Status": constants.SAFE_DELETE_CABLE_STATUS,
            "Safe Delete Prefix Status": constants.SAFE_DELETE_PREFIX_STATUS,
            "Disabled Sync Objects": ", ".join(disabled_keys()) or "None",
        }

    # pylint: disable-next=too-many-arguments, arguments-differ
    def run(self, *args, **kwargs):
        """Run the job."""
        self.kwargs = {
            "snapshot": kwargs.get("snapshot"),
            "dryrun": kwargs.get("dryrun"),
            "safe_delete_mode": kwargs.get("safe_delete_mode"),
            "sync_ipfabric_tagged_only": kwargs.get("sync_ipfabric_tagged_only"),
            "bulk_write_mode": kwargs.get("bulk_write_mode"),
            "strict": strict_mode.StrictObjects.from_job_kwargs(kwargs),
            "location_filter": kwargs.get("location_filter"),
            "tenant": kwargs.get("tenant"),
            "namespace": kwargs.get("namespace"),
            "debug": kwargs.get("debug"),
            "scope": SyncScope.from_job_kwargs(kwargs),
        }
        self.dryrun = kwargs.get("dryrun")
        self.memory_profiling = kwargs.get("memory_profiling")
        self.parallel_loading = kwargs.get("parallel_loading")
        # Nautobot instantiates a Device Type's component templates on a Device's first save. A
        # batched insert never calls save(), so a Device written in a batch gets none of them, but a
        # batch the database refuses is retried an object at a time and those saves would. Suppressed
        # for the run, so a Device's components do not depend on whether the batch it fell in was
        # refused, and the Interfaces IP Fabric reports are not left colliding with templated ones.
        # Read by `sync_data`, so it has to be set before the base class runs it.
        self.skip_auto_component_creation = bool(kwargs.get("bulk_write_mode"))
        try:
            super().run(*args, **kwargs)
        finally:
            # `sync_data` sets it for the run; cleared after, so nothing outside a run can read it.
            nbutils.use_namespace(None)

    def load_source_adapter(self):
        """Not used."""

    def load_target_adapter(self):
        """Not used."""

    def warn_if_the_synced_tag_was_renamed(self):
        """Warn when the configured synced Tag is unused while the default one still marks objects."""
        left_behind = nbutils.objects_left_on_the_default_synced_tag()
        if left_behind:
            self.logger.warning(
                "No object carries the '%s' Tag yet, while %d carry '%s'. If this replaces a sync that "
                "used '%s', rename that Tag to '%s' in Nautobot so its objects stay in scope. A second "
                "IP Fabric instance with a Tag of its own can ignore this.",
                constants.SYNCED_TAG_NAME,
                left_behind,
                constants.DEFAULT_SYNCED_TAG_NAME,
                constants.DEFAULT_SYNCED_TAG_NAME,
                constants.SYNCED_TAG_NAME,
            )

    def log_run_options(self, options: str, scope: SyncScope, strict: strict_mode.StrictObjects):
        """Log the options the run started with, and what its scope and strictness leave out."""
        self.logger.info(f"Starting job with the following options: {options}")
        self.logger.info("Object types in scope: %s", scope.describe())
        self.logger.info("Object types matched rather than created: %s", strict.describe())
        for explanation in (*scope.explanations(), *strict.explanations(scope)):
            self.logger.warning(explanation)
        self.warn_if_the_synced_tag_was_renamed()

    def sync_data(self, *_args, **_kwargs):
        """Sync a device data from IP Fabric into Nautobot."""
        error = None
        if self.client is None:
            self.client, error = self._init_ipf_client()
        if self.client is None:
            self.logger.error("IP Fabric client is not ready: %s", error)
            return

        # Thread local and shared by every run in this worker. A run that failed part way through
        # leaves them populated, holding objects that may belong to a transaction that rolled back,
        # so a run starts by emptying them rather than trusting the last one to have finished.
        job_scoped_cache.clear_all()

        self.client.snapshot_id = self.kwargs["snapshot"]
        dryrun = self.kwargs["dryrun"]
        safe_mode = self.kwargs["safe_delete_mode"]
        tagged_only = self.kwargs["sync_ipfabric_tagged_only"]
        bulk_write_mode = self.kwargs["bulk_write_mode"]
        strict = self.kwargs["strict"]
        scope = self.kwargs["scope"]
        location_filter = self.kwargs["location_filter"]
        debug_mode = self.kwargs["debug"]
        tenant = Tenant.objects.get(pk=self.kwargs["tenant"]) if self.kwargs.get("tenant") else None
        namespace = Namespace.objects.get(pk=self.kwargs["namespace"]) if self.kwargs.get("namespace") else None
        # Set on every run, None included, so that a Namespace chosen for the last run in this
        # worker is not inherited by this one.
        nbutils.use_namespace(namespace)

        if location_filter:
            location_filter_object = Location.objects.get(pk=location_filter)
        else:
            location_filter_object = None
        options = f"`Snapshot_id`: {self.client.snapshot_id}.`Debug`: {debug_mode}, `Dry Run`: {dryrun}, `Safe Delete Mode`: {safe_mode}, `Sync Tagged Only`: {tagged_only}, `Bulk Write Mode`: {bulk_write_mode}, `Location Filter`: {location_filter_object}, `Tenant`: {tenant}, `Namespace`: {nbutils.get_run_namespace()}"
        self.log_run_options(options, scope, strict)

        ipfabric_source = IPFabricDiffSync(
            job=self,
            sync=self.sync,
            client=self.client,
            location_filter=location_filter_object.name if location_filter_object else None,
            scope=scope,
            strict=strict,
            tenant=tenant,
            safe_delete_mode=safe_mode,
        )
        self.logger.info("Loading current data from IP Fabric...")
        ipfabric_source.load()

        # Constructed after the source has loaded, so that the addresses it could not find a subnet
        # for are known and this side can withhold the same ones.
        dest = NautobotDiffSync(
            job=self,
            sync=self.sync,
            sync_ipfabric_tagged_only=tagged_only,
            bulk_write_mode=bulk_write_mode,
            safe_delete_mode=safe_mode,
            location_filter=location_filter_object,
            scope=scope,
            strict=strict,
            tenant=tenant,
            addresses_without_a_subnet=ipfabric_source.addresses_without_a_subnet,
            interfaces_without_admin_state=ipfabric_source.interfaces_without_admin_state,
            devices_without_a_hardware_serial=ipfabric_source.devices_without_a_hardware_serial,
            interfaces_without_a_type=ipfabric_source.interfaces_without_a_type,
            devices_without_a_software_version=ipfabric_source.devices_without_a_software_version,
            devices_without_a_software_image=ipfabric_source.devices_without_a_software_image,
        )

        self.logger.info("Loading current data from Nautobot...")
        dest.load()
        self.logger.info("Calculating diffs...")

        diff = dest.diff_from(ipfabric_source)
        # pylint: disable-next=logging-fstring-interpolation
        if debug_mode:
            self.logger.debug("Diff: %s", diff.dict())

        self.sync.diff = diff.dict()
        self.sync.save()
        create = diff.summary().get("create")
        update = diff.summary().get("update")
        delete = diff.summary().get("delete")
        no_change = diff.summary().get("no-change")
        self.logger.info(
            f"DiffSync Summary: Create: {create}, Update: {update}, Delete: {delete}, No Change: {no_change}"
        )
        if not dryrun:
            self.logger.info("Syncing from IP Fabric to Nautobot")
            try:
                dest.sync_from(ipfabric_source, flags=DiffSyncFlags.CONTINUE_ON_FAILURE)
            except ObjectNotCreated:
                self.logger.debug("Unable to create object.", exc_info=True)

        self.logger.info("Sync complete.")


jobs = [IpFabricDataSource]
