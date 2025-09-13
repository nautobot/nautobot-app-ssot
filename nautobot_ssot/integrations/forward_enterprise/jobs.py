"""Forward Enterprise DataSource job class."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from nautobot.core.utils.lookup import get_route_for_model
from nautobot.extras.jobs import BooleanVar, Job, ObjectVar
from nautobot.extras.models import ExternalIntegration
from nautobot.ipam.models import Namespace

from nautobot_ssot.contrib.sorting import sort_relationships
from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.forward_enterprise import ForwardEnterpriseAdapter
from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.nautobot import NautobotDiffSyncAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SSoT - Forward Enterprise"  # pylint: disable=invalid-name


class ForwardEnterpriseDataSource(DataSource, Job):
    """Forward Enterprise Single Source of Truth Data Source.

    Synchronizes network device information from Forward Enterprise to Nautobot,
    including devices, interfaces, and IPAM data based on configured options.
    """

    credentials = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="name",
        required=True,
        label="Forward Enterprise Instance",
        description="Forward Enterprise External Integration with API credentials and configuration.",
    )

    namespace = ObjectVar(
        model=Namespace,
        queryset=Namespace.objects.all(),
        display_field="name",
        required=False,
        label="IPAM Namespace",
        description="Namespace to use for imported IPAM objects from Forward Enterprise. If unspecified, will use 'Global' Namespace.",
    )

    sync_interfaces = BooleanVar(
        default=False,
        label="Sync Interfaces",
        description="Enable synchronization of device interfaces from Forward Enterprise.",
    )

    sync_ipam = BooleanVar(
        default=False,
        label="Sync IPAM Data",
        description="Enable synchronization of prefixes, IP addresses, and VLANs from Forward Enterprise.",
    )

    delete_objects = BooleanVar(
        default=False,
        label="Delete Unmatched Objects",
        description="Enable deletion of objects in Nautobot that no longer exist in Forward Enterprise. "
        "WARNING: This will permanently delete devices, interfaces, and IPAM objects not found in Forward Enterprise. "
        "Use with caution in production environments.",
    )

    def __init__(self, *args, **kwargs):
        """Initialize the ForwardEnterpriseDataSource job."""
        super().__init__(*args, **kwargs)
        # Initialize kwargs attribute to avoid pylint warning
        self.kwargs = {}

    class Meta:
        """Metadata for the ForwardEnterpriseDataSource job."""

        name = "Forward Enterprise ⟹ Nautobot"
        data_source = "Forward Enterprise"
        data_source_icon = static("nautobot_ssot_forward_enterprise/forwardnetworks.png")
        description = "Sync network device information from Forward Enterprise to Nautobot"
        has_sensitive_variables = False

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource.

        Returns:
            tuple: List of DataMapping objects describing sync operations
        """
        return (
            DataMapping("Location", None, "Location", get_route_for_model(model="dcim.location", action="list")),
            DataMapping(
                "Manufacturer", None, "Manufacturer", get_route_for_model(model="dcim.manufacturer", action="list")
            ),
            DataMapping(
                "Device Type", None, "Device Type", get_route_for_model(model="dcim.devicetype", action="list")
            ),
            DataMapping("Platform", None, "Platform", get_route_for_model(model="dcim.platform", action="list")),
            DataMapping("Role", None, "Role", get_route_for_model(model="extras.role", action="list")),
            DataMapping("Device", None, "Device", get_route_for_model(model="dcim.device", action="list")),
            DataMapping("Interface", None, "Interface", get_route_for_model(model="dcim.interface", action="list")),
            DataMapping("VRF", None, "VRF", get_route_for_model(model="ipam.vrf", action="list")),
            DataMapping("Prefix", None, "Prefix", get_route_for_model(model="ipam.prefix", action="list")),
            DataMapping("IP Address", None, "IP Address", get_route_for_model(model="ipam.ipaddress", action="list")),
            DataMapping("VLAN", None, "VLAN", get_route_for_model(model="ipam.vlan", action="list")),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource.

        Returns:
            dict: Configuration information for display in UI
        """
        return {
            "Default Device Role": constants.DEFAULT_DEVICE_ROLE,
            "Default Device Role Color": constants.DEFAULT_DEVICE_ROLE_COLOR,
            "Default Device Status": constants.DEFAULT_DEVICE_STATUS,
            "Default Device Status Color": constants.DEFAULT_DEVICE_STATUS_COLOR,
            "Default Interface Status": constants.DEFAULT_INTERFACE_STATUS,
            "Default Prefix Status": constants.DEFAULT_PREFIX_STATUS,
            "Default IP Address Status": constants.DEFAULT_IPADDRESS_STATUS,
            "Default VLAN Status": constants.DEFAULT_VLAN_STATUS,
            "System of Record": constants.SYSTEM_OF_RECORD,
            "API Timeout": f"{constants.DEFAULT_API_TIMEOUT} seconds",
            "VLAN Group Template": constants.VLAN_GROUP_NAME_TEMPLATE,
            "Deletion Behavior": "Configurable via 'Delete Unmatched Objects' parameter",
            "Safe Mode": "Objects not in Forward Enterprise are preserved by default",
        }

    def load_source_adapter(self):
        """Load the source adapter: Forward Enterprise.

        Initializes the Forward Enterprise adapter with API credentials and configuration
        from the External Integration object.
        """
        self.logger.info("Loading source adapter: Forward Enterprise")

        # Get the actual values that will be passed to the adapter
        sync_interfaces_value = bool(
            self.kwargs.get("sync_interfaces") if hasattr(self, "kwargs") else getattr(self, "sync_interfaces", False)
        )
        sync_ipam_value = bool(
            self.kwargs.get("sync_ipam") if hasattr(self, "kwargs") else getattr(self, "sync_ipam", False)
        )

        # Log the effective adapter flags for clarity
        self.logger.info(
            "Source adapter flags: sync_interfaces=%s, sync_ipam=%s",
            sync_interfaces_value,
            sync_ipam_value,
        )

        self.source_adapter = ForwardEnterpriseAdapter(
            job=self,
            sync_interfaces=sync_interfaces_value,
            sync_ipam=sync_ipam_value,
        )
        # Pass namespace to adapter for IPAM operations
        self.source_adapter.namespace = self.namespace
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load the target adapter: Nautobot.

        Initializes the Nautobot adapter that represents the current state
        of objects in the Nautobot database.
        """
        self.logger.info("Loading target adapter: Nautobot")
        self.target_adapter = NautobotDiffSyncAdapter(job=self)
        self.target_adapter.load()

        # Sort relationships after both adapters are loaded (source is loaded before target)
        if hasattr(self, "source_adapter") and self.source_adapter:
            self.logger.info("Sorting relationships for consistent ordering...")
            sort_relationships(self.source_adapter, self.target_adapter)

    # pylint: disable=too-many-arguments, arguments-differ, too-many-positional-arguments
    def run(
        self,
        dryrun,
        sync_interfaces,
        sync_ipam,
        credentials,
        namespace,
        delete_objects,
        memory_profiling,
        *args,
        **kwargs,
    ):
        """Run the Forward Enterprise DataSource job.

        Args:
            dryrun (bool): Whether to perform a dry run (no actual changes)
            memory_profiling (bool): Whether to enable memory profiling
            credentials (ExternalIntegration): Forward Enterprise credentials
            namespace (Namespace): IPAM namespace for imported objects
            sync_interfaces (bool): Enable interface synchronization
            sync_ipam (bool): Enable IPAM synchronization
            delete_objects (bool): Enable deletion of unmatched objects in Nautobot
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
        """
        self.logger.info("Running Forward Enterprise DataSource job")

        # Store job parameters as instance attributes
        self.credentials = credentials
        self.namespace = namespace
        if not self.namespace:
            self.namespace = Namespace.objects.get(name="Global")

        # Configure DiffSync flags based on delete_objects parameter
        if delete_objects:
            # Allow deletions - Forward Enterprise is the true source of record
            self.logger.warning(
                "DELETE MODE ENABLED: Objects in Nautobot with Forward Enterprise as the Set as Source of Truth that are not found in Forward Enterprise will be DELETED. "
                "This action is irreversible."
            )
            # Remove SKIP_UNMATCHED_DST flag to allow deletions
            # The absence of this flag means unmatched destination objects will be deleted
        else:
            # Skip unmatched destination objects (default safe behavior)
            self.diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST
            self.logger.info(
                "SAFE MODE: Objects in Nautobot that are not found in Forward Enterprise will be preserved. "
                "To enable deletions, use the 'Delete Unmatched Objects' option."
            )

        # Store sync options in kwargs for access by adapters
        # Always use tagged-only mode for Forward Enterprise integration
        self.kwargs = {
            "sync_forward_tagged_only": True,  # Always use tagged-only mode
            "sync_interfaces": sync_interfaces,
            "sync_ipam": sync_ipam,
            "delete_objects": delete_objects,
        }

        # Call parent run method to execute the sync
        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)


jobs = [ForwardEnterpriseDataSource]
