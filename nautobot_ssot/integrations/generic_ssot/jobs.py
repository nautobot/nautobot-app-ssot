"""Jobs for Generic SSoT Integration."""

import logging

from diffsync.enum import DiffSyncFlags
from nautobot.apps.jobs import IntegerVar, MultiObjectVar, ObjectVar
from nautobot.core.celery import register_jobs
from nautobot.extras.jobs import Job
from nautobot.extras.models import ExternalIntegration

from nautobot_ssot.integrations.generic_ssot.diffsync.adapters.external import GenericExternalAdapter
from nautobot_ssot.integrations.generic_ssot.diffsync.adapters.nautobot import GenericNautobotAdapter
from nautobot_ssot.integrations.generic_ssot.models import (
    SSOTDataSample,
    SSOTEndpoint,
    SSOTSyncConfig,
)
from nautobot_ssot.integrations.generic_ssot.utils import (
    fetch_data_from_endpoint_definition,
    validate_endpoint_ordering,
)
from nautobot_ssot.jobs.base import DataSource

logger = logging.getLogger("nautobot.ssot")

name = "Generic SSoT"  # pylint: disable=invalid-name


class GenericSSOTDataCollectionJob(Job):
    """Fetch sample data from external API endpoints and store per-endpoint SSOTDataSample records."""

    integration = ObjectVar(
        model=ExternalIntegration,
        queryset=ExternalIntegration.objects.all(),
        display_field="display",
        required=True,
        label="External Integration",
        description="The external integration (base URL + auth) to collect data from.",
    )
    endpoints = MultiObjectVar(
        model=SSOTEndpoint,
        required=True,
        label="Endpoints",
        description="Select one or more SSoT Endpoints to fetch sample data from.",
    )
    sample_size = IntegerVar(
        required=False,
        label="Sample Size",
        description="Maximum number of records to fetch per endpoint (0 = no limit).",
        default=100,
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Generic SSoT Data Collection."""

        name = "Generic SSoT Data Collection"
        description = (
            "Fetch sample data from external API endpoints and save per-endpoint data samples for the mapping builder."
        )
        has_sensitive_variables = False

    def run(self, integration, endpoints, sample_size=100, **kwargs):  # pylint: disable=arguments-differ
        """Execute the data collection job."""
        if not endpoints:
            self.logger.error("No endpoints selected. Nothing to collect.")
            return

        sample_size = sample_size or 0  # treat None as unlimited

        for endpoint in endpoints:
            self.logger.info("Fetching data from endpoint: %s (%s)", endpoint.name, endpoint.api_path)
            ep_dict = endpoint.to_endpoint_dict()

            try:
                records, total_count = fetch_data_from_endpoint_definition(
                    integration=integration,
                    endpoint_def=ep_dict,
                    sample_size=sample_size if sample_size > 0 else None,
                    logger=self.logger,
                )
                self.logger.info(
                    "Endpoint '%s': fetched %d records.",
                    endpoint.name,
                    len(records),
                )

                # Infer field names and types from sample records.
                discovered_fields = {}
                for record in records[:20]:
                    if isinstance(record, dict):
                        for key, value in record.items():
                            if key not in discovered_fields:
                                discovered_fields[key] = type(value).__name__

                SSOTDataSample.objects.update_or_create(
                    endpoint=endpoint,
                    defaults={
                        "sample_data": records,
                        "discovered_fields": discovered_fields,
                        "total_record_count": total_count,
                    },
                )
                self.logger.info(
                    "SSOTDataSample updated for endpoint '%s'.",
                    endpoint.name,
                )
            except Exception as exc:
                self.logger.error("Failed to fetch from endpoint '%s': %s", endpoint.name, exc)


class GenericSSOTDataSource(DataSource):
    """Import data from an external API into Nautobot using a Generic SSoT Sync Config."""

    sync_config = ObjectVar(
        model=SSOTSyncConfig,
        queryset=SSOTSyncConfig.objects.filter(enabled=True),
        display_field="name",
        required=True,
        label="Sync Config",
        description="Select a Generic SSoT Sync Config to run.",
    )

    class Meta:  # pylint: disable=too-few-public-methods
        """Meta data for Generic SSoT."""

        name = "Generic SSoT Sync"
        data_source = "External API"
        data_target = "Nautobot"
        description = "Sync data from an external API into Nautobot using a configured SSoT Sync Config."
        has_sensitive_variables = False

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        return {
            "Sync Configs": "Manage under Plugins > SSoT > Generic SSoT Configs.",
            "Endpoints": "Define API endpoints under Plugins > SSoT > SSoT Endpoints.",
            "Field Mappings": "Build field mappings from the Sync Config detail page.",
        }

    def load_source_adapter(self):
        """Load data from the external API into DiffSync models."""
        self.source_adapter = GenericExternalAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.source_adapter.load()

    def load_target_adapter(self):
        """Load data from Nautobot into DiffSync models."""
        self.target_adapter = GenericNautobotAdapter(
            job=self,
            sync=self.sync,
            sync_config=self.sync_config,
        )
        self.target_adapter.load()

    def run(  # pylint: disable=arguments-differ
        self,
        dryrun,
        memory_profiling,
        sync_config,
        *args,
        **kwargs,
    ):
        """Perform data synchronization."""
        self.sync_config = sync_config

        if not sync_config.field_mappings.filter(enabled=True).exists():
            self.logger.error(
                "Sync Config '%s' has no enabled field mappings. Configure field mappings first.",
                sync_config.name,
            )
            return

        # Validate endpoint ordering and log warnings for unsatisfiable FK dependencies.
        ordering_warnings = validate_endpoint_ordering(sync_config, logger=self.logger)
        if ordering_warnings:
            self.logger.warning(
                "Endpoint ordering may cause FK resolution issues (%d warning(s)).",
                len(ordering_warnings),
            )

        self.dryrun = dryrun
        self.memory_profiling = memory_profiling

        # Prevent deletion of Nautobot objects not present in the external source
        # unless the sync config explicitly opts in.
        if not getattr(sync_config, "delete_unmatched", False):
            self.diffsync_flags |= DiffSyncFlags.SKIP_UNMATCHED_DST

        super().run(dryrun=self.dryrun, memory_profiling=self.memory_profiling, *args, **kwargs)


jobs = [GenericSSOTDataCollectionJob, GenericSSOTDataSource]
register_jobs(*jobs)
