"""Jobs for Infoblox integration with SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.extras.choices import SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
from nautobot.extras.jobs import BooleanVar
from nautobot.apps.jobs import ObjectVar
from nautobot_ssot.jobs.base import DataMapping, DataSource, DataTarget
from nautobot_ssot.models import SSOTInfobloxConfig

from .diffsync.adapters import infoblox, nautobot
from .utils.client import InfobloxApi


name = "SSoT - Infoblox DDI"  # pylint: disable=invalid-name


def _get_infoblox_client_config(app_config, debug):
    """Get Infoblox client config from the Infoblox config instance."""
    username = app_config.infoblox_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    password = app_config.infoblox_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    infoblox_client_config = {
        "url": app_config.infoblox_instance.remote_url,
        "username": username,
        "password": password,
        "verify_ssl": app_config.infoblox_instance.verify_ssl,
        "wapi_version": app_config.infoblox_wapi_version,
        "timeout": app_config.infoblox_instance.timeout,
        "debug": debug,
        "network_view_to_dns_map": app_config.infoblox_dns_view_mapping,
    }

    return infoblox_client_config


class InfobloxDataSource(DataSource):
    """Infoblox SSoT Data Source."""

    debug = BooleanVar(description="Enable for verbose debug logging.")
    config = ObjectVar(
        model=SSOTInfobloxConfig,
        display_field="SSOT Infoblox config",
        required=True,
        query_params={
            "enable_sync_to_nautobot": True,
            "job_enabled": True,
        },
    )

    def __init__(self):
        """Initialize InfobloxDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Infoblox ⟹ Nautobot"
        data_source = "Infoblox"
        data_source_icon = static("nautobot_ssot_infoblox/infoblox_logo.png")
        description = "Sync infomation from Infoblox to Nautobot"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Infoblox and Nautobot."""
        return (
            DataMapping("network_view", None, "Namespace", reverse("ipam:namespace_list")),
            DataMapping("network", None, "Prefix", reverse("ipam:prefix_list")),
            DataMapping("ipaddress", None, "IP Address", reverse("ipam:ipaddress_list")),
            DataMapping("vlan", None, "VLAN", reverse("ipam:vlan_list")),
            DataMapping("vlanview", None, "VLANGroup", reverse("ipam:vlangroup_list")),
        )

    def load_source_adapter(self):
        """Load Infoblox data."""
        self.logger.info("Connecting to Infoblox")
        client_config = _get_infoblox_client_config(self.config, self.debug)
        client = InfobloxApi(**client_config)
        self.source_adapter = infoblox.InfobloxAdapter(job=self, sync=self.sync, conn=client, config=self.config)
        self.logger.info("Loading data from Infoblox...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot data."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, config=self.config)
        self.logger.info("Loading data from Nautobot...")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.config = kwargs.get("config")
        if not self.config.enable_sync_to_nautobot:
            self.logger.error("Can't run sync to Nautobot, provided config doesn't have it enabled...")
            raise ValueError("Config not enabled for sync to Nautobot.")
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


class InfobloxDataTarget(DataTarget):
    """Infoblox SSoT Data Target."""

    debug = BooleanVar(description="Enable for verbose debug logging.")
    config = ObjectVar(
        model=SSOTInfobloxConfig,
        display_field="SSOT Infoblox config",
        required=True,
        query_params={
            "enable_sync_to_infoblox": True,
            "job_enabled": True,
        },
    )

    def __init__(self):
        """Initialize InfobloxDataTarget."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:  # pylint: disable=too-few-public-methods
        """Information about the Job."""

        name = "Nautobot ⟹ Infoblox"
        data_target = "Infoblox"
        data_target_icon = static("nautobot_ssot_infoblox/infoblox_logo.png")
        description = "Sync infomation from Nautobot to Infoblox"

    @classmethod
    def data_mappings(cls):
        """Show mapping of models between Nautobot and Infoblox."""
        return (
            DataMapping("Namespace", reverse("ipam:namespace_list"), "network_view", None),
            DataMapping("Prefix", reverse("ipam:prefix_list"), "network", None),
            DataMapping("IP Address", reverse("ipam:ipaddress_list"), "ipaddress", None),
            DataMapping("VLAN", reverse("ipam:vlan_list"), "vlan", None),
            DataMapping("VLANGroup", reverse("ipam:vlangroup_list"), "vlanview", None),
        )

    def load_source_adapter(self):
        """Load Nautobot data."""
        self.logger.info("Connecting to Nautobot...")
        self.source_adapter = nautobot.NautobotAdapter(job=self, sync=self.sync, config=self.config)
        self.logger.info("Loading data from Nautobot...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Infoblox data."""
        self.logger.info("Connecting to Infoblox")
        client_config = _get_infoblox_client_config(self.config, self.debug)
        client = InfobloxApi(**client_config)
        self.target_adapter = infoblox.InfobloxAdapter(job=self, sync=self.sync, conn=client, config=self.config)
        self.logger.info("Loading data from Infoblox...")
        self.target_adapter.load()

    def run(self, dryrun, memory_profiling, debug, *args, **kwargs):  # pylint: disable=arguments-differ
        """Perform data synchronization."""
        self.debug = debug
        self.dryrun = dryrun
        self.config = kwargs.get("config")
        # Additional guard against launching sync to Infoblox with config that doesn't allow it
        if not self.config.enable_sync_to_infoblox:
            self.logger.error("Can't run sync to Infoblox, provided config doesn't have it enabled...")
            raise ValueError("Config not enabled for sync to Infoblox.")
        self.memory_profiling = memory_profiling
        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [InfobloxDataSource, InfobloxDataTarget]
