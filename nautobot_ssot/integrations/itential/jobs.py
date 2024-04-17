"""Itential SSoT Jobs."""

from datetime import datetime

from django.forms import HiddenInput

from nautobot.dcim.models import Location
from nautobot.extras.jobs import BooleanVar, ObjectVar, Job

from nautobot_ssot.jobs.base import DataTarget
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.itential.clients import AutomationGatewayClient
from nautobot_ssot.integrations.itential.diffsync.adapters.itential import ItentialAnsibleDeviceAdapter
from nautobot_ssot.integrations.itential.diffsync.adapters.nautobot import NautobotAnsibleDeviceAdapter


name = "SSoT - Itential"  # pylint: disable=invalid-name


class ItentialAutomationGatewayDataTarget(DataTarget, Job):
    """Job syncing Nautobot to Itential Automation Gateway."""

    dryrun = BooleanVar(default=False, widget=HiddenInput(), required=True)
    location = ObjectVar(model=Location, description="Choose a location to sync to.", required=True)
    location_descendants = BooleanVar(default=True, required=True)

    class Meta:
        """Meta class definition."""

        name = "Nautobot ⟹ Itential Automation Gateway"
        data_target = "Itential Automation Gateway"
        # data_source_icon = static("nautobot_ssot_itential/itential.png")
        description = "Sync data from Nautobot into Itential Automation Gateway."
        field_order = ("location", "location_descendants", "dry_run")

    @property
    def gateways(self):
        """Fetch Automation Gateways to sync."""
        self.logger.info(f"Loading gateays for {self.location}.")
        gateways = AutomationGatewayClient.objects.filter(enabled=True, location=self.location)
        return gateways

    def load_source_adapter(self, location: Location, location_descendants: bool):
        """Load Nautobot adapter."""
        self.source_adapter = NautobotAnsibleDeviceAdapter(
            job=self, sync=self.sync, location=location, location_descendants=location_descendants
        )
        self.logger.info("Loading data from Nautobot.")
        self.source_adapter.load()

    def load_target_adapter(self, api_client: AutomationGatewayClient):
        """Load Itential adapter."""
        self.target_adapter = ItentialAnsibleDeviceAdapter(job=self, sync=self.sync, api_client=api_client)
        self.logger.info("Loading data from Itential.")
        self.target_adapter.load()

    def sync_data(self, memory_profiling):
        """Execute Nautobot ⟹ Itential Automation Gateway sync."""

        def record_memory_trace(step: str):
            """Helper function to record memory usage and reset tracemalloc stats."""
            memory_final, memory_peak = tracemalloc.get_traced_memory()
            setattr(self.sync, f"{step}_memory_final", memory_final)
            setattr(self.sync, f"{step}_memory_peak", memory_peak)
            self.sync.save()
            self.logger.info("Traced memory for %s (Final, Peak): %s bytes, %s bytes", step, memory_final, memory_peak)
            tracemalloc.clear_traces()

        if not self.sync:
            return

        if memory_profiling:
            tracemalloc.start()

        start_time = datetime.now()

        self.logger.info("Loading current data from source adapter...")
        self.load_source_adapter(location=self.location, location_descendants=self.location_descendants)
        load_source_adapter_time = datetime.now()
        self.sync.source_load_time = load_source_adapter_time - start_time
        self.sync.save()
        self.logger.info("Source Load Time from %s: %s", self.source_adapter, self.sync.source_load_time)

        if memory_profiling:
            record_memory_trace("source_load")

        for device in self.gateways:
            with AutomationGatewayClient(
                host=device.gateway.remote_url,
                username=device.gateway.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
                ),
                password=device.gateway.secrets_group.get_secret_value(
                    access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                    secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
                ),
                job=self,
                verify_ssl=device.gateway.verify_ssl,
            ) as api_client:
                self.logger.info("Loading current data from target adapter.")
                self.load_target_adapter(api_client=api_client)
                load_target_adapter_time = datetime.now()
                self.sync.target_load_time = load_target_adapter_time - load_source_adapter_time
                self.sync.save()
                self.logger.info("Target Load Time from %s: %s", self.target_adapter, self.sync.target_load_time)

                if memory_profiling:
                    record_memory_trace("target_load")

                self.logger.info("Calculating diffs...")
                self.calculate_diff()
                calculate_diff_time = datetime.now()
                self.sync.diff_time = calculate_diff_time - load_target_adapter_time
                self.sync.save()
                self.logger.info("Diff Calculation Time: %s", self.sync.diff_time)

                if memory_profiling:
                    record_memory_trace("diff")

                if self.dryrun:
                    self.logger.info("As `dryrun` is set, skipping the actual data sync.")
                else:
                    self.logger.info("Syncing from %s to %s...", self.source_adapter, self.target_adapter)
                    self.execute_sync()
                    execute_sync_time = datetime.now()
                    self.sync.sync_time = execute_sync_time - calculate_diff_time
                    self.sync.save()
                    self.logger.info("Sync complete")
                    self.logger.info("Sync Time: %s", self.sync.sync_time)

                    if memory_profiling:
                        record_memory_trace("sync")

    def run(self, dryrun, memory_profiling, location, location_descendants, *args, **kwargs):
        """Execute sync."""
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        self.location = location
        self.location_descendants = location_descendants
        super().__init__(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [ItentialAutomationGatewayDataTarget]
