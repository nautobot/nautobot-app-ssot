"""Slurpit DataSource job class."""

import asyncio

import slurpit
from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar, Job, ObjectVar
from nautobot.extras.models import ExternalIntegration

from nautobot_ssot.integrations.slurpit import constants
from nautobot_ssot.integrations.slurpit.diffsync.adapters.nautobot import NautobotDiffSyncAdapter
from nautobot_ssot.integrations.slurpit.diffsync.adapters.slurpit import SlurpitAdapter
from nautobot_ssot.jobs.base import DataMapping, DataSource

loop = asyncio.new_event_loop()


# Step 3 - the job
class SlurpitDataSource(DataSource, Job):
    """SSoT Job class."""

    credentials = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="name",
        required=True,
        label="Slurpit Instance",
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
        self.target_adapter = NautobotDiffSyncAdapter(job=self, data=self.kwargs)
        self.target_adapter.load()

    # pylint: disable-next=too-many-arguments, arguments-differ
    def run(
        self,
        dryrun,
        memory_profiling,
        credentials,
        sync_slurpit_tagged_only,
        *args,
        **kwargs,
    ):
        """Run the Slurpit DataSource job."""
        self.logger.info("Running Slurpit DataSource job")
        self.credentials = credentials
        self.kwargs = {
            "sync_slurpit_tagged_only": sync_slurpit_tagged_only,
        }
        super().run(dryrun=dryrun, memory_profiling=memory_profiling, *args, **kwargs)


jobs = [SlurpitDataSource]
