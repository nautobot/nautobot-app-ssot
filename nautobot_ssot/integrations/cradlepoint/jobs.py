#  pylint: disable=keyword-arg-before-vararg
#  pylint: disable=too-few-public-methods
#  pylint: disable=too-many-locals
#  pylint: disable=abstract-method

"""Job for Cradlepoint integration with SSoT app."""

from diffsync.enum import DiffSyncFlags
from django.templatetags.static import static
from django.urls import reverse
from nautobot.apps.jobs import BooleanVar, IntegerVar, ObjectVar
from nautobot.extras.choices import (
    SecretsGroupAccessTypeChoices,
    SecretsGroupSecretTypeChoices,
)

from nautobot_ssot.integrations.cradlepoint.constants import DEFAULT_API_DEVICE_LIMIT
from nautobot_ssot.integrations.cradlepoint.diffsync.adapters.cradlepoint import CradlepointSourceAdapter
from nautobot_ssot.integrations.cradlepoint.diffsync.adapters.nautobot import NautobotTargetAdapter
from nautobot_ssot.integrations.cradlepoint.models import SSOTCradlepointConfig
from nautobot_ssot.integrations.cradlepoint.utilities.clients import (
    CradlepointClient,
)
from nautobot_ssot.jobs.base import DataMapping, DataSource

name = "SSoT - Cradlepoint"  # pylint: disable=invalid-name


def get_cradlepoint_client_config(app_config, debug):
    """Get Cradlepoint client config from the Cradlepoint config instance."""
    x_ecm_api_id = app_config.cradlepoint_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_USERNAME,
    )
    x_ecm_api_key = app_config.cradlepoint_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_PASSWORD,
    )
    x_cp_api_id = app_config.cradlepoint_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_SECRET,
    )
    x_cp_api_key = app_config.cradlepoint_instance.secrets_group.get_secret_value(
        access_type=SecretsGroupAccessTypeChoices.TYPE_REST,
        secret_type=SecretsGroupSecretTypeChoices.TYPE_TOKEN,
    )
    return {
        "base_url": app_config.cradlepoint_instance.remote_url,
        "x_ecm_api_id": x_ecm_api_id.strip(),
        "x_ecm_api_key": x_ecm_api_key.strip(),
        "x_cp_api_id": x_cp_api_id.strip(),
        "x_cp_api_key": x_cp_api_key.strip(),
        "verify_ssl": app_config.cradlepoint_instance.verify_ssl,
        "debug": debug,
        "page_limit": 100,
    }


# pylint:disable=too-few-public-methods
class CradlepointDataSource(DataSource):  # pylint: disable=too-many-instance-attributes
    """Cradlepoint SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging")
    config = ObjectVar(
        model=SSOTCradlepointConfig,
        display_field="SSOT Cradlepoint Config",
        required=True,
        query_params={"job_enabled": True},
    )

    # NOTE: Probably not needed, offset to be determined by `page_limit * page`
    starting_offset = IntegerVar(
        default=0,
        description=f"Starting offset for pagination in retrieval of devices. Current pagination is set at {DEFAULT_API_DEVICE_LIMIT}.",
        label="Starting Offset",
        required=True,
    )

    def __init__(self):
        """Initialize CradlepointDataSource."""
        super().__init__()
        self.diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

    class Meta:
        """Metadata about this Job."""

        name = "Cradlepoint ⟹ Nautobot"
        data_source = "Cradlepoint"
        data_source_icon = static("nautobot_ssot_cradlepoint/cradlepoint_logo.png")
        description = "Sync data from Cradlepoint into Nautobot."

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {"Instances": "Found in Extensibility -> External Integrations menu."}

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping(
                "Router",
                None,
                "Device",
                reverse("dcim:device_list"),
            ),
        )

    def run(
        self,
        dryrun,
        config,
        starting_offset,
        memory_profiling,
        debug,
        *args,
        **kwargs,
    ):  # pylint: disable=arguments-differ, too-many-arguments
        """Run sync."""
        self.dryrun = dryrun
        self.debug = debug
        self.memory_profiling = memory_profiling
        self.config = config
        self.starting_offset = starting_offset
        super().run(dryrun, memory_profiling, *args, **kwargs)

    def load_source_adapter(self):
        """Load Cradlepoint adapter."""
        self.logger.info("Connecting to Cradlepoint.")
        self.source_adapter = CradlepointSourceAdapter(
            job=self,
            sync=self.sync,
            client=CradlepointClient(
                **get_cradlepoint_client_config(self.config, self.debug)
            ),
            config=self.config,
            starting_offset=self.starting_offset,
        )
        self.logger.info("Loading data from Cradlepoint...")
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load Nautobot Adapter."""
        self.logger.info("Connecting to Nautobot...")
        self.target_adapter = NautobotTargetAdapter(
            job=self,
            sync=self.sync,
            config=self.config,
        )

        self.logger.info("Loading current data from Nautobot...")
        self.target_adapter.load()


jobs = [CradlepointDataSource]
