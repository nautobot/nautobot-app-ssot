"""Forward Enterprise DataSource job class."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from nautobot.core.utils.lookup import get_route_for_model
from nautobot.extras.jobs import BooleanVar, Job, ObjectVar
from nautobot.extras.models import ExternalIntegration
from nautobot.ipam.models import Namespace, Prefix

from nautobot_ssot.contrib.sorting import sort_relationships
from nautobot_ssot.integrations.forward_enterprise import constants
from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.forward_enterprise import ForwardEnterpriseAdapter
from nautobot_ssot.integrations.forward_enterprise.diffsync.adapters.nautobot import NautobotDiffSyncAdapter
from nautobot_ssot.integrations.forward_enterprise.diffsync.models.models import NautobotPrefixModel
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
        # Initialize sync flags as instance attributes (will be set in run())
        self.sync_interfaces = False
        self.sync_ipam = False
        self.delete_objects = False

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

        # Log the effective adapter flags for clarity
        self.logger.info(
            "Source adapter flags: sync_interfaces=%s, sync_ipam=%s",
            self.sync_interfaces,
            self.sync_ipam,
        )

        self.source_adapter = ForwardEnterpriseAdapter(
            job=self,
            sync_interfaces=self.sync_interfaces,
            sync_ipam=self.sync_ipam,
            namespace=self.namespace,
        )
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

        # Store job parameters as instance attributes (standard pattern from Device42/ACI)
        self.credentials = credentials
        self.namespace = namespace
        self.sync_interfaces = sync_interfaces
        self.sync_ipam = sync_ipam
        self.delete_objects = delete_objects

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

        # Call parent run method to execute the sync
        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)

    def execute_sync(self):
        """Execute the sync and then assign VRFs to prefixes that were created during sync.

        This overrides the base execute_sync to add a post-sync VRF assignment phase.
        This is necessary because DiffSync doesn't guarantee that VRF objects are created
        in the database before Prefix objects try to reference them, even though VRFs
        appear before Prefixes in the top_level list.
        """
        # First, execute the normal sync
        super().execute_sync()

        # Then, assign VRFs to any prefixes that are missing VRF assignments
        # This ensures VRFs are properly linked even if they were created in the same sync
        self._assign_vrfs_to_prefixes()

    def _assign_vrfs_to_prefixes(self):
        """Assign VRFs to prefixes after sync completes.

        During the sync phase, Prefix.create() may try to assign VRFs that don't exist yet
        in the Nautobot database. This method retries VRF assignment for all prefixes that
        have VRF references in the source adapter but failed to get VRFs assigned during
        the initial create.

        Uses the shared _assign_vrfs_to_prefix() method from NautobotPrefixModel to ensure
        consistent logic and eliminate code duplication (DRY principle).
        """
        if not self.source_adapter or not hasattr(self.source_adapter, "get_all"):
            return

        self.logger.info("Post-sync: Assigning VRFs to prefixes...")

        total_assigned = 0
        total_failed = 0
        prefixes_processed = 0

        try:
            # Get all prefix models from the source adapter
            prefix_models = list(self.source_adapter.get_all("prefix"))

            for prefix_model in prefix_models:
                # Skip prefixes without VRF references
                if not prefix_model.vrfs:
                    continue

                try:
                    # Get the actual Django Prefix object
                    django_prefix = Prefix.objects.get(
                        network=prefix_model.network,
                        prefix_length=prefix_model.prefix_length,
                        namespace__name=prefix_model.namespace__name,
                    )

                    # Check if prefix already has VRFs assigned
                    current_vrf_count = django_prefix.vrfs.count()
                    expected_vrf_count = len(prefix_model.vrfs)

                    # If VRF count matches, skip this prefix
                    if current_vrf_count == expected_vrf_count:
                        continue

                    # Use shared method to assign VRFs (eliminates code duplication)
                    assigned, failed = NautobotPrefixModel._assign_vrfs_to_prefix(
                        django_prefix=django_prefix,
                        vrfs=prefix_model.vrfs,
                        adapter=self.source_adapter,
                        log_prefix="Post-sync: ",
                    )

                    total_assigned += assigned
                    total_failed += failed
                    if assigned > 0 or failed > 0:
                        prefixes_processed += 1

                except Prefix.DoesNotExist:
                    # Prefix doesn't exist - this is fine, might have been deleted or not created
                    continue
                except Exception as e:
                    self.logger.warning(
                        f"Error assigning VRFs to prefix {prefix_model.network}/{prefix_model.prefix_length}: {e}"
                    )
                    total_failed += 1

        except Exception as e:
            self.logger.error(f"Error during post-sync VRF assignment: {e}")
            return

        # Log summary
        if total_assigned > 0:
            self.logger.info(
                f"Post-sync: Assigned {total_assigned} VRF-to-Prefix relationship(s) across {prefixes_processed} prefix(es)"
            )
        if total_failed > 0:
            self.logger.warning(f"Post-sync: Failed to assign {total_failed} VRF-to-Prefix relationship(s)")
        if total_assigned == 0 and total_failed == 0:
            self.logger.info("Post-sync: No VRF assignments needed (all prefixes already have correct VRFs)")


jobs = [ForwardEnterpriseDataSource]
