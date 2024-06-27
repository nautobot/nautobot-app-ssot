"""Itential SSoT Jobs."""

from nautobot.extras.models import Status
from nautobot.extras.jobs import ObjectVar

from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot_ssot.jobs.base import DataTarget

from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.itential.clients import AutomationGatewayClient
from nautobot_ssot.integrations.itential.diffsync.adapters.itential import ItentialAnsibleDeviceAdapter
from nautobot_ssot.integrations.itential.diffsync.adapters.nautobot import NautobotAnsibleDeviceAdapter


name = "SSoT - Itential"  # pylint: disable=invalid-name


class ItentialAutomationGatewayDataTarget(DataTarget):  # pylint: disable=too-many-instance-attributes
    """Job syncing Nautobot to Itential Automation Gateway."""

    gateway = ObjectVar(model=AutomationGatewayModel, description="Choose a gateway to sync to.", required=True)
    status = ObjectVar(model=Status, description="Choose a device status to sync.", required=True)

    class Meta:
        """Meta class definition."""

        name = "Nautobot ⟹ Itential Automation Gateway"
        data_target = "Itential Automation Gateway"
        # data_source_icon = static("nautobot_ssot_itential/itential.png")
        description = "Sync data from Nautobot into Itential Automation Gateway."
        has_sensitive_variables = False

    def load_source_adapter(self):
        """Load Nautobot adapter."""
        self.source_adapter = NautobotAnsibleDeviceAdapter(
            job=self,
            sync=self.sync,
            gateway=self.gateway,
            status=self.status,
        )
        self.logger.info("Loading data from Nautobot.")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Itential adapter."""
        if not self.gateway.enabled:
            self.logger.warning(f"{self.gateway.gateway.remote_url} is not enabled to sync inventory.")
            return

        api_client = AutomationGatewayClient(
            host=self.gateway.gateway.remote_url,
            username=self.gateway.gateway.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
            ),
            password=self.gateway.gateway.secrets_group.get_secret_value(
                access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
                secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
            ),
            job=self,
            verify_ssl=self.gateway.gateway.verify_ssl,
        )
        api_client.login()

        self.target_adapter = ItentialAnsibleDeviceAdapter(job=self, sync=self.sync, api_client=api_client)
        self.logger.info("Loading data from Itential.")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, gateway, status, *args, **kwargs):  # pylint: disable=arguments-differ
        """Execute sync."""
        self.gateway = gateway
        self.status = status
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [ItentialAutomationGatewayDataTarget]
