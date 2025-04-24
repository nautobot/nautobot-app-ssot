# pylint: disable=R0801
"""Slurpit DataSource job class."""

import slurpit
from diffsync.enum import DiffSyncFlags
from django.contrib.contenttypes.models import ContentType
from django.templatetags.static import static
from django.urls import reverse
from nautobot.dcim.models import Device, LocationType
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar, Job, ObjectVar
from nautobot.extras.models import ExternalIntegration
from nautobot.ipam.models import Namespace

from nautobot_ssot.integrations.slurpit import constants
from nautobot_ssot.integrations.slurpit.diffsync.adapters.nautobot import NautobotDiffSyncAdapter
from nautobot_ssot.integrations.slurpit.diffsync.adapters.slurpit import SlurpitAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource


class SlurpitDataSource(DataSource, Job):  # pylint: disable=too-many-instance-attributes
    """SSoT Job class."""

    credentials = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="name",
        required=True,
        label="Slurpit Instance",
    )

    site_loctype = ObjectVar(
        model=LocationType,
        queryset=LocationType.objects.all(),
        display_field="name",
        required=False,
        label="Site LocationType",
        description="LocationType to use for imported Sites from Slurpit. If unspecified, will revert to Site LocationType.",
    )

    namespace = ObjectVar(
        model=Namespace,
        queryset=Namespace.objects.all(),
        display_field="name",
        required=False,
        label="IPAM Namespace",
        description="Namespace to use for imported IPAM objects from Slurpit. If unspecified, will revert to Global Namespace.",
    )

    ignore_prefixes = BooleanVar(
        default=True,
        label="Ignore Routing Table Prefixes",
        description="Ignore some prefixes that are used for routing tables and not IPAM such as 0.0.0.0/0.",
    )

    sync_slurpit_tagged_only = BooleanVar(
        default=True,
        label="Sync tagged objects only",
        description="Only sync objects that have the 'SSoT Synced from Slurpit' Tag.",
    )

    kwargs = {}

    class Meta:
        """Metadata for the SlurpitDataSource job."""

        name = "Slurpit Data Source"
        description = "Sync information from Slurpit to Nautobot."
        data_source = "Slurpit"
        data_source_icon = static("nautobot_ssot_slurpit/slurpit.png")
        has_sensitive_variables = False

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Site", None, "Location", reverse("dcim:location_list")),
            DataMapping("Manufacturer", None, "Manufacturer", reverse("dcim:manufacturer_list")),
            DataMapping("Device Type", None, "Device Type", reverse("dcim:devicetype_list")),
            DataMapping("Platform", None, "Platform", reverse("dcim:platform_list")),
            DataMapping("Role", None, "Role", reverse("extras:role_list")),
            DataMapping("Device", None, "Device", reverse("dcim:device_list")),
            DataMapping("Interface", None, "Interface", reverse("dcim:interface_list")),
            DataMapping("IP Address", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("Prefix", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("VLAN", None, "VLAN", reverse("ipam:vlan_list")),
            DataMapping("VRF", None, "VRF", reverse("ipam:vrf_list")),
        )

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration options for this DataSource."""
        return {
            "Default Device Role": constants.DEFAULT_DEVICE_ROLE,
            "Default Device Role Color": constants.DEFAULT_DEVICE_ROLE_COLOR,
            "Default Device Status": constants.DEFAULT_DEVICE_STATUS,
            "Default Device Status Color": constants.DEFAULT_DEVICE_STATUS_COLOR,
        }

    def load_source_adapter(self):
        """Load the source adapter."""
        self.logger.info("Loading source adapter: Slurpit")
        token = self.credentials.secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP, secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN
        )
        client = slurpit.api(url=self.credentials.remote_url, api_key=token, verify=self.credentials.verify_ssl)
        self.source_adapter = SlurpitAdapter(api_client=client, job=self)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load the target adapter."""
        self.logger.info("Loading target adapter: Nautobot")
        self.target_adapter = NautobotDiffSyncAdapter(job=self)
        self.target_adapter.load()

    # pylint: disable-next=too-many-arguments, arguments-differ
    def run(
        self,
        dryrun,
        memory_profiling,
        credentials,
        site_loctype,
        namespace,
        ignore_prefixes,
        sync_slurpit_tagged_only,
        *args,
        **kwargs,
    ):
        """Run the Slurpit DataSource job."""
        self.logger.info("Running Slurpit DataSource job")
        self.credentials = credentials
        self.site_loctype = site_loctype
        if not self.site_loctype:
            self.site_loctype = LocationType.objects.get_or_create(name="Site")[0]
        self.site_loctype.content_types.add(ContentType.objects.get_for_model(Device))
        self.namespace = namespace
        if not self.namespace:
            self.namespace = Namespace.objects.get(name="Global")
        self.ignore_prefixes = ignore_prefixes

        self.diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST

        self.kwargs = {
            "sync_slurpit_tagged_only": sync_slurpit_tagged_only,
        }
        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)


jobs = [SlurpitDataSource]
