#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
"""IP Fabric Data Target Job."""
import uuid
from diffsync.enum import DiffSyncFlags
from diffsync.exceptions import ObjectNotCreated
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from httpx import ConnectError
from ipfabric import IPFClient
from nautobot.dcim.models import Site
from nautobot.extras.jobs import BooleanVar, Job, ScriptVariable, ChoiceVar
from nautobot.utilities.forms import DynamicModelChoiceField
from nautobot_ssot.jobs.base import DataMapping, DataSource

from nautobot_ssot_ipfabric.diffsync.adapter_ipfabric import IPFabricDiffSync
from nautobot_ssot_ipfabric.diffsync.adapter_nautobot import NautobotDiffSync
from nautobot_ssot_ipfabric.diffsync.adapters_shared import DiffSyncModelAdapters
from nautobot_ssot_ipfabric.diffsync.diffsync_models import DiffSyncExtras

CONFIG = settings.PLUGINS_CONFIG.get("nautobot_ssot_ipfabric", {})
IPFABRIC_HOST = CONFIG["ipfabric_host"]
IPFABRIC_API_TOKEN = CONFIG["ipfabric_api_token"]
IPFABRIC_SSL_VERIFY = CONFIG["ipfabric_ssl_verify"]
IPFABRIC_TIMEOUT = CONFIG["ipfabric_timeout"]
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


def get_formatted_snapshots(client):
    """Get all loaded snapshots and format them for display in choice menu.

    Returns:
        dict: Snapshot objects as dict of tuples {snapshot_ref: (description, snapshot_id)}
    """
    formatted_snapshots = {}
    snapshot_refs = []
    if client:
        client.update()
        for snapshot_ref, snapshot in client.snapshots.items():
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
class IpFabricDataSource(DataSource, Job):
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
        description="Only sync objects that have the 'ssot-synced-from-ipfabric' tag.",
    )
    site_filter = OptionalObjectVar(
        description="Only sync Nautobot records belonging to a single Site. This does not filter IPFabric data.",
        model=Site,
        required=False,
    )

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
            "dry_run",
        )

    @classmethod
    def _get_vars(cls):
        """Extend JobDataSource._get_vars to include some variables.

        This also initializes them.
        """
        got_vars = super()._get_vars()

        if cls.snapshot is None:
            try:
                cls.client = IPFClient(
                    base_url=IPFABRIC_HOST,
                    token=IPFABRIC_API_TOKEN,
                    verify=IPFABRIC_SSL_VERIFY,
                    timeout=IPFABRIC_TIMEOUT,
                )
            except (RuntimeError, ConnectError) as error:
                print(f"Got an error {error}")
                cls.client = None

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
            DataMapping("Site", None, "Site", reverse("dcim:site_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
            DataMapping("VLANs", None, "VLANs", reverse("ipam:vlan_list")),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "IP Fabric host": CONFIG["ipfabric_host"],
            "Default MAC Address": CONFIG.get("default_interface_mac", "00:00:00:00:00:01"),
            "Default Device Role": CONFIG.get("default_device_role", "Network Device"),
            "Default Interface Type": CONFIG.get("default_interface_type", "1000base-t"),
            "Default Device Status": CONFIG.get("default_device_status", "Active"),
            "Allow Duplicate Addresses": CONFIG.get("allow_duplicate_addresses", True),
            "Default MTU": CONFIG.get("default_interface_mtu", 1500),
            "Nautobot Host URL": CONFIG.get("nautobot_host"),
            "Safe Delete Device Status": CONFIG.get("safe_delete_device_status", "Deprecated"),
            "Safe Delete Site Status": CONFIG.get("safe_delete_site_status", "Decommissioning"),
            "Safe Delete IPAddress Status": CONFIG.get("safe_ipaddress_interfaces_status", "Deprecated"),
            "Safe Delete VLAN status": CONFIG.get("safe_delete_vlan_status", "Inventory"),
        }

    def log_debug(self, message):
        """Conditionally log a debug message."""
        if self.kwargs.get("debug"):
            super().log_debug(message)

    def load_source_adapter(self):
        """Not used."""

    def load_target_adapter(self):
        """Not used."""

    def sync_data(self):
        """Sync a device data from IP Fabric into Nautobot."""
        if self.client is None:
            self.log_failure(message="IPFabric client is not ready. Check your config.")
            return

        self.client.snapshot_id = self.kwargs["snapshot"]
        dry_run = self.kwargs["dry_run"]
        safe_mode = self.kwargs["safe_delete_mode"]
        tagged_only = self.kwargs["sync_ipfabric_tagged_only"]
        site_filter = self.kwargs["site_filter"]
        debug_mode = self.kwargs["debug"]

        if site_filter:
            site_filter_object = Site.objects.get(pk=site_filter)
        else:
            site_filter_object = None
        options = f"`Snapshot_id`: {self.client.snapshot_id}.`Debug`: {debug_mode}, `Dry Run`: {dry_run}, `Safe Delete Mode`: {safe_mode}, `Sync Tagged Only`: {tagged_only}, `Site Filter`: {site_filter_object}"
        self.log_info(message=f"Starting job with the following options: {options}")

        ipfabric_source = IPFabricDiffSync(job=self, sync=self.sync, client=self.client)
        self.log_info(message="Loading current data from IP Fabric...")
        ipfabric_source.load()

        # Set safe mode either way (Defaults to True)
        DiffSyncModelAdapters.safe_delete_mode = safe_mode
        DiffSyncExtras.safe_delete_mode = safe_mode

        dest = NautobotDiffSync(
            job=self,
            sync=self.sync,
            sync_ipfabric_tagged_only=tagged_only,
            site_filter=site_filter_object,
        )

        self.log_info(message="Loading current data from Nautobot...")
        dest.load()

        self.log_info(message="Calculating diffs...")
        flags = DiffSyncFlags.CONTINUE_ON_FAILURE

        diff = dest.diff_from(ipfabric_source, flags=flags)
        self.log_debug(message=f"Diff: {diff.dict()}")

        self.sync.diff = diff.dict()
        self.sync.save()
        create = diff.summary().get("create")
        update = diff.summary().get("update")
        delete = diff.summary().get("delete")
        no_change = diff.summary().get("no-change")
        self.log_info(
            message=f"DiffSync Summary: Create: {create}, Update: {update}, Delete: {delete}, No Change: {no_change}"
        )
        if not dry_run:
            self.log_info(message="Syncing from IP Fabric to Nautobot")
            try:
                dest.sync_from(ipfabric_source)
            except ObjectNotCreated as err:
                self.log_debug(f"Unable to create object. {err}")

        self.log_success(message="Sync complete.")


jobs = [IpFabricDataSource]
