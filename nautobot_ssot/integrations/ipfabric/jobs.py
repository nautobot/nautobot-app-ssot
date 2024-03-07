#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
"""IP Fabric Data Target Job."""
import uuid
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectNotCreated
from django.templatetags.static import static
from django.urls import reverse
from httpx import ConnectError
from ipfabric import IPFClient
from nautobot.dcim.models import Location
from nautobot.extras.jobs import BooleanVar, ScriptVariable, ChoiceVar
from nautobot.core.forms import DynamicModelChoiceField
from nautobot_ssot.jobs.base import DataMapping, DataSource

from nautobot_ssot.integrations.ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot.integrations.ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot.integrations.ipfabric.diffsync.diffsync_models import DiffSyncExtras
from nautobot_ssot.integrations.ipfabric import constants


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
        description="Only sync objects that have the 'SSoT Synced from IPFabric' Tag.",
    )
    location_filter = OptionalObjectVar(
        description="Only sync Nautobot records belonging to a single Location. This does not filter IPFabric data.",
        model=Location,
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
            "dryrun",
        )

    @staticmethod
    def _init_ipf_client():
        try:
            return IPFClient(
                base_url=constants.IPFABRIC_HOST,
                token=constants.IPFABRIC_API_TOKEN,
                verify=constants.IPFABRIC_SSL_VERIFY,
                timeout=constants.IPFABRIC_TIMEOUT,
                unloaded=False,
            )
        except (RuntimeError, ConnectError) as error:
            print(f"Got an error {error}")
            return None

    @classmethod
    def _get_vars(cls):
        """Extend JobDataSource._get_vars to include some variables.

        This also initializes them.
        """
        got_vars = super()._get_vars()

        if cls.client is None:
            cls.client = cls._init_ipf_client()
        else:
            cls.client.update()

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

        return got_vars

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Device", None, "Device", reverse("dcim:device_list")),
            DataMapping("Location", None, "Location", reverse("dcim:location_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
            DataMapping("VLANs", None, "VLANs", reverse("ipam:vlan_list")),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "IP Fabric host": constants.IPFABRIC_HOST,
            "Nautobot Host URL": constants.NAUTOBOT_HOST,
            "Default Device Role": constants.DEFAULT_DEVICE_ROLE,
            "Default Device Role Color": constants.DEFAULT_DEVICE_ROLE_COLOR,
            "Default Device Status": constants.DEFAULT_DEVICE_STATUS,
            "Default Device Status Color": constants.DEFAULT_DEVICE_STATUS_COLOR,
            "Default Interface Type": constants.DEFAULT_INTERFACE_TYPE,
            "Default MAC Address": constants.DEFAULT_INTERFACE_MAC,
            "Default MTU": constants.DEFAULT_INTERFACE_MTU,
            "Allow Duplicate Addresses": constants.ALLOW_DUPLICATE_ADDRESSES,
            "Safe Delete Device Status": constants.SAFE_DELETE_DEVICE_STATUS,
            "Safe Delete Location Status": constants.SAFE_DELETE_LOCATION_STATUS,
            "Safe Delete IPAddress Status": constants.SAFE_DELETE_IPADDRESS_STATUS,
            "Safe Delete VLAN status": constants.SAFE_DELETE_VLAN_STATUS,
        }

    # pylint: disable-next=too-many-arguments, arguments-differ
    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        snapshot=None,
        safe_delete_mode=True,
        sync_ipfabric_tagged_only=True,
        location_filter=None,
        *args,
        **kwargs,
    ):
        """Run the job."""
        self.kwargs = {
            "snapshot": snapshot,
            "dryrun": dryrun,
            "safe_delete_mode": safe_delete_mode,
            "sync_ipfabric_tagged_only": sync_ipfabric_tagged_only,
            "location_filter": location_filter,
            "debug": debug,
        }

        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)

    def load_source_adapter(self):
        """Not used."""

    def load_target_adapter(self):
        """Not used."""

    def sync_data(self, *_args, **_kwargs):
        """Sync a device data from IP Fabric into Nautobot."""
        if self.client is None:
            self.client = self._init_ipf_client()
        if self.client is None:
            self.logger.error("IPFabric client is not ready. Check your config.")
            return

        self.client.snapshot_id = self.kwargs["snapshot"]
        dryrun = self.kwargs["dryrun"]
        safe_mode = self.kwargs["safe_delete_mode"]
        tagged_only = self.kwargs["sync_ipfabric_tagged_only"]
        location_filter = self.kwargs["location_filter"]
        debug_mode = self.kwargs["debug"]

        if location_filter:
            location_filter_object = Location.objects.get(pk=location_filter)
        else:
            location_filter_object = None
        options = f"`Snapshot_id`: {self.client.snapshot_id}.`Debug`: {debug_mode}, `Dry Run`: {dryrun}, `Safe Delete Mode`: {safe_mode}, `Sync Tagged Only`: {tagged_only}, `Location Filter`: {location_filter_object}"
        self.logger.info(f"Starting job with the following options: {options}")

        ipfabric_source = IPFabricDiffSync(job=self, sync=self.sync, client=self.client)
        self.logger.info("Loading current data from IP Fabric...")
        ipfabric_source.load()

        # Set safe mode either way (Defaults to True)
        DiffSyncModelAdapters.safe_delete_mode = safe_mode
        DiffSyncExtras.safe_delete_mode = safe_mode

        dest = NautobotDiffSync(
            job=self,
            sync=self.sync,
            sync_ipfabric_tagged_only=tagged_only,
            location_filter=location_filter_object,
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
