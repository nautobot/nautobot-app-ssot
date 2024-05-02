"""Jobs for DNA Center SSoT integration."""

from django.urls import reverse
from django.templatetags.static import static
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar, ObjectVar
from nautobot.extras.models import ExternalIntegration
from nautobot.tenancy.models import Tenant
from nautobot.core.celery import register_jobs
from nautobot_ssot.jobs.base import DataSource, DataMapping
from nautobot_ssot_dna_center.diffsync.adapters import dna_center, nautobot
from nautobot_ssot_dna_center.utils.dna_center import DnaCenterClient


name = "DNA Center SSoT"  # pylint: disable=invalid-name


class DnaCenterDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """DNA Center SSoT Data Source."""

    dnac = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        required=True,
        label="DNAC Instance",
    )
    debug = BooleanVar(description="Enable for more verbose debug logging", default=False)
    bulk_import = BooleanVar(description="Perform bulk operations when importing data", default=False)
    tenant = ObjectVar(model=Tenant, label="Tenant", required=False)

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for DNA Center."""

        name = "DNA Center to Nautobot"
        data_source = "DNA Center"
        data_target = "Nautobot"
        description = "Sync information from DNA Center to Nautobot"
        data_source_icon = static("nautobot_ssot_dna_center/dna_center_logo.png")

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {"Instances": "Found in Extensibility -> External Integrations menu."}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("Areas", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Buildings", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Floors", None, "Locations", reverse("dcim:location_list")),
            DataMapping("Devices", None, "Devices", reverse("dcim:device_list")),
            DataMapping("Interfaces", None, "Interfaces", reverse("dcim:interface_list")),
            DataMapping("IP Addresses", None, "IP Addresses", reverse("ipam:ipaddress_list")),
        )

    def load_source_adapter(self):
        """Load data from DNA Center into DiffSync models."""
        self.logger.info(f"Loading data from {self.dnac.name}")
        _sg = self.dnac.secrets_group
        username = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
        )
        password = _sg.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_HTTP,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
        )
        client = DnaCenterClient(
            url=self.dnac.remote_url,
            username=username,
            password=password,
            port=self.dnac.extra_config["port"],
            verify=self.dnac.verify_ssl,
        )
        client.connect()
        self.source_adapter = dna_center.DnaCenterAdapter(job=self, sync=self.sync, client=client, tenant=self.tenant)
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, tenant=self.tenant)
        self.target_adapter.load()

    def run(
        self,
        dryrun,
        memory_profiling,
        debug,
        dnac,
        bulk_import,
        tenant,
        *args,
        **kwargs,  # pylint: disable=arguments-differ, too-many-arguments
    ):
        """Perform data synchronization."""
        self.dnac = dnac
        self.tenant = tenant
        self.debug = debug
        self.bulk_import = bulk_import
        self.dryrun = dryrun
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [DnaCenterDataSource]
register_jobs(*jobs)
