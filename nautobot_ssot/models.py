"""
Django Models for recording the status and progress of data synchronization between data sources.

The interaction between these models and Nautobot's native JobResult model deserves some examination.

- A JobResult is created each time a data sync is requested.
  - This stores a reference to the specific sync operation requested (JobResult.name),
    much as a Job-related JobResult would reference the name of the Job.
  - This stores a 'job_id', which this plugin uses to reference the specific sync instance.
  - This stores the 'created' and 'completed' timestamps, and the requesting user (if any)
  - This stores the overall 'status' of the job (pending, running, completed, failed, errored.)
  - This stores a 'data' field which, in theory can store arbitrary JSON data, but in practice
    expects a fairly strict structure for logging of various status messages.
    This field is therefore not suitable for storage of in-depth data synchronization log messages,
    which have a different set of content requirements, but is used for high-level status reporting.

JobResult 1<->1 Sync 1-->n SyncLogEntry
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.timezone import now

from nautobot.core.models import BaseModel
from nautobot.extras.models import JobResult
from nautobot.extras.utils import extras_features

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices


@extras_features(
    "custom_links",
)
class Sync(BaseModel):
    """High-level overview of a data sync event/process/attempt.

    Essentially an extension of the JobResult model to add a few additional fields.
    """

    source = models.CharField(max_length=64, help_text="System data is read from")
    target = models.CharField(max_length=64, help_text="System data is written to")

    start_time = models.DateTimeField(blank=True, null=True)
    # end_time is represented by the job_result.completed field
    source_load_time = models.DurationField(blank=True, null=True)
    target_load_time = models.DurationField(blank=True, null=True)
    diff_time = models.DurationField(blank=True, null=True)
    sync_time = models.DurationField(blank=True, null=True)
    source_load_memory_final = models.PositiveBigIntegerField(blank=True, null=True)
    source_load_memory_peak = models.PositiveBigIntegerField(blank=True, null=True)
    target_load_memory_final = models.PositiveBigIntegerField(blank=True, null=True)
    target_load_memory_peak = models.PositiveBigIntegerField(blank=True, null=True)
    diff_memory_final = models.PositiveBigIntegerField(blank=True, null=True)
    diff_memory_peak = models.PositiveBigIntegerField(blank=True, null=True)
    sync_memory_final = models.PositiveBigIntegerField(blank=True, null=True)
    sync_memory_peak = models.PositiveBigIntegerField(blank=True, null=True)

    dry_run = models.BooleanField(
        default=False, help_text="Report what data would be synced but do not make any changes"
    )
    diff = models.JSONField(blank=True)

    job_result = models.ForeignKey(to=JobResult, on_delete=models.PROTECT, blank=True, null=True)

    class Meta:
        """Metaclass attributes of Sync model."""

        ordering = ["start_time"]

    def __str__(self):
        """String representation of a Sync instance."""
        return f"{self.source} → {self.target}, {date_format(self.start_time, format=settings.SHORT_DATETIME_FORMAT)}"

    def get_absolute_url(self):
        """Get the detail-view URL for this instance."""
        return reverse("plugins:nautobot_ssot:sync", kwargs={"pk": self.pk})

    @classmethod
    def annotated_queryset(cls):
        """Construct an efficient queryset for this model and related data."""
        return (
            cls.objects.defer("diff")
            .select_related("job_result")
            .prefetch_related("logs")
            .annotate(
                num_unchanged=models.Count(
                    "log", filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_NO_CHANGE)
                ),
                num_created=models.Count("log", filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_CREATE)),
                num_updated=models.Count("log", filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_UPDATE)),
                num_deleted=models.Count("log", filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_DELETE)),
                num_succeeded=models.Count(
                    "log", filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_SUCCESS)
                ),
                num_failed=models.Count("log", filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_FAILURE)),
                num_errored=models.Count("log", filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_ERROR)),
            )
        )

    @property
    def duration(self):
        """Total execution time of this Sync."""
        if not self.start_time:
            return timedelta()  # zero
        if not self.job_result or not self.job_result.completed:
            return now() - self.start_time
        return self.job_result.completed - self.start_time

    def get_source_url(self):
        """Get the absolute url of the source worker associated with this instance."""
        if self.source == "Nautobot" or not self.job_result:
            return None
        return reverse(
            "plugins:nautobot_ssot:data_source",
            kwargs={"class_path": self.job_result.name},
        )

    def get_target_url(self):
        """Get the absolute url of the target worker associated with this instance."""
        if self.target == "Nautobot" or not self.job_result:
            return None
        return reverse(
            "plugins:nautobot_ssot:data_target",
            kwargs={"class_path": self.job_result.name},
        )


class SyncLogEntry(BaseModel):
    """Record of a single event during a data sync operation.

    Detailed sync logs are recorded in this model, rather than in JobResult.data, because
    JobResult.data imposes fairly strict expectations about the structure of its contents
    that do not align well with the requirements of this plugin. Also, storing log entries as individual
    database records rather than a single JSON blob allows us to filter, query, sort, etc. as desired.

    This model somewhat "shadows" Nautobot's built-in ObjectChange model; the key distinction to
    bear in mind is that an ObjectChange reflects a change that *did happen*, while a SyncLogEntry
    may reflect this or may reflect a change that *could not happen* or *failed*.
    Additionally, if we're syncing data from Nautobot to a different system as data target,
    the data isn't changing in Nautobot, so there will be no ObjectChange record.
    """

    sync = models.ForeignKey(to=Sync, on_delete=models.CASCADE, related_name="logs", related_query_name="log")
    timestamp = models.DateTimeField(auto_now_add=True)

    action = models.CharField(max_length=32, choices=SyncLogEntryActionChoices)
    status = models.CharField(max_length=32, choices=SyncLogEntryStatusChoices)
    diff = models.JSONField(blank=True, null=True)

    synced_object_type = models.ForeignKey(
        to=ContentType,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    synced_object_id = models.UUIDField(blank=True, null=True)
    synced_object = GenericForeignKey(ct_field="synced_object_type", fk_field="synced_object_id")

    object_repr = models.CharField(max_length=200, blank=True, default="", editable=False)

    message = models.CharField(max_length=511, blank=True)

    class Meta:
        """Metaclass attributes of SyncLogEntry."""

        verbose_name_plural = "sync log entries"
        ordering = ["sync", "timestamp"]

    def get_action_class(self):
        """Map self.action to a Bootstrap label class."""
        return {
            SyncLogEntryActionChoices.ACTION_NO_CHANGE: "default",
            SyncLogEntryActionChoices.ACTION_CREATE: "success",
            SyncLogEntryActionChoices.ACTION_UPDATE: "info",
            SyncLogEntryActionChoices.ACTION_DELETE: "warning",
        }.get(self.action)

    def get_status_class(self):
        """Map self.status to a Bootstrap label class."""
        return {
            SyncLogEntryStatusChoices.STATUS_SUCCESS: "success",
            SyncLogEntryStatusChoices.STATUS_FAILURE: "warning",
            SyncLogEntryStatusChoices.STATUS_ERROR: "danger",
        }.get(self.status)
