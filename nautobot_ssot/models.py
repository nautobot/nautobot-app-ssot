"""
Django Models for recording the status and progress of data synchronization between data sources.

The interaction between these models and Nautobot's native JobResult model deserves some examination.

- A JobResult is created each time a data sync is requested.
  - This stores a reference to the specific sync operation requested (JobResult.name),
    much as a Job-related JobResult would reference the name of the Job.
  - This stores a 'job_id', which this app uses to reference the specific sync instance.
  - This stores the 'created' and 'completed' timestamps, and the requesting user (if any)
  - This stores the overall 'status' of the job (pending, running, completed, failed, errored.)
  - This stores a 'data' field which, in theory can store arbitrary JSON data, but in practice
    expects a fairly strict structure for logging of various status messages.
    This field is therefore not suitable for storage of in-depth data synchronization log messages,
    which have a different set of content requirements, but is used for high-level status reporting.

JobResult 1<->1 Sync 1-->n SyncLogEntry
"""

import logging
from datetime import timedelta

from diffsync.enum import DiffSyncFlags
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.timezone import now
from django_enum import EnumField
from nautobot.apps.constants import CHARFIELD_MAX_LENGTH
from nautobot.apps.models import BaseModel
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult, StatusField
from nautobot.extras.utils import extras_features

from nautobot_ssot.integrations.infoblox.models import SSOTInfobloxConfig
from nautobot_ssot.integrations.itential.models import AutomationGatewayModel
from nautobot_ssot.integrations.servicenow.models import SSOTServiceNowConfig
from nautobot_ssot.templatetags.shorter_timedelta import shorter_timedelta

from .choices import (
    SyncLogEntryActionChoices,
    SyncLogEntryStatusChoices,
    SyncRecordActionChoices,
)

logger = logging.getLogger(__name__)


class DiffJSONEncoder(DjangoJSONEncoder):
    """Custom JSON encoder for the Sync.diff field."""

    def default(self, o):
        """Custom JSON encoder for the Sync.diff field."""
        if isinstance(o, set):
            return self.encode(list(o))
        return super().default(o)


@extras_features(
    "custom_links",
)
class Sync(BaseModel):  # pylint: disable=nb-string-field-blank-null
    """High-level overview of a data sync event/process/attempt.

    Essentially an extension of the JobResult model to add a few additional fields.
    """

    source = models.CharField(max_length=64, help_text="System data is read from", verbose_name="Data Source")
    target = models.CharField(max_length=64, help_text="System data is written to", verbose_name="Data Target")

    start_time = models.DateTimeField(blank=True, null=True, db_index=True)
    # end_time is represented by the job_result.date_done field
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
        default=False,
        help_text="Report what data would be synced but do not make any changes",
        verbose_name="Type",
    )
    diff = models.JSONField(blank=True, encoder=DiffJSONEncoder)
    summary = models.JSONField(blank=True, null=True)

    job_result = models.ForeignKey(to=JobResult, on_delete=models.CASCADE, blank=True, null=True)
    hide_in_diff_view = True

    class Meta:
        """Metaclass attributes of Sync model."""

        ordering = ["start_time"]
        verbose_name = "Data Sync"
        verbose_name_plural = "SSoT Sync History"

    def __str__(self):
        """String representation of a Sync instance."""
        return f"{self.source} → {self.target}, {date_format(self.start_time, format=settings.SHORT_DATETIME_FORMAT)}"

    def get_absolute_url(self, api=False):
        """Get the detail-view URL for this instance."""
        return reverse("plugins:nautobot_ssot:sync", kwargs={"pk": self.pk})

    @classmethod
    def annotated_queryset(cls):
        """Construct an efficient queryset for this model and related data."""
        return (
            cls.objects.defer("diff", "summary")
            .select_related("job_result")
            .annotate(
                num_unchanged=models.Count(
                    "log",
                    filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_NO_CHANGE),
                ),
                num_created=models.Count(
                    "log",
                    filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_CREATE),
                ),
                num_updated=models.Count(
                    "log",
                    filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_UPDATE),
                ),
                num_deleted=models.Count(
                    "log",
                    filter=models.Q(log__action=SyncLogEntryActionChoices.ACTION_DELETE),
                ),
                num_succeeded=models.Count(
                    "log",
                    filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_SUCCESS),
                ),
                num_failed=models.Count(
                    "log",
                    filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_FAILURE),
                ),
                num_errored=models.Count(
                    "log",
                    filter=models.Q(log__status=SyncLogEntryStatusChoices.STATUS_ERROR),
                ),
            )
        )

    @property
    def duration(self):  # pylint: disable=inconsistent-return-statements
        """Total execution time of this Sync."""
        if not self.start_time:
            return timedelta()  # zero
        if not self.job_result or self.job_result.status == JobResultStatusChoices.STATUS_PENDING:
            return now() - self.start_time
        if self.job_result and self.job_result.date_done:
            return self.job_result.date_done - self.start_time

    @property
    def end_time(self):
        """End time of this Sync, if known."""
        if self.job_result and self.job_result.date_done:
            return self.job_result.date_done
        return None

    def get_source_url(self):
        """Get the absolute url of the source worker associated with this instance."""
        if self.source == "Nautobot" or not self.job_result:
            return None
        return reverse(
            "plugins:nautobot_ssot:data_source",
            kwargs={"class_path": self.job_result.job_model.class_path},
        )

    def get_source_display(self):
        """Display the name and link to the source worker associated with this instance."""
        source_url = self.get_source_url()
        if source_url:
            return format_html('<a href="{}">{}</a>', source_url, self.source)
        return self.source

    def get_target_url(self):
        """Get the absolute url of the target worker associated with this instance."""
        if self.target == "Nautobot" or not self.job_result:
            return None
        return reverse(
            "plugins:nautobot_ssot:data_target",
            kwargs={"class_path": self.job_result.job_model.class_path},
        )

    def get_target_display(self):
        """Display the name and link to the target worker associated with this instance."""
        target_url = self.get_target_url()
        if target_url:
            return format_html('<a href="{}">{}</a>', target_url, self.target)
        return self.target

    def get_duration_display(self):
        """Display the duration of this Sync and each phase."""
        return format_html(
            """
                {} total
                <ul>
                    <li>{} loading from {}</li>
                    <li>{} loading from {}</li>
                    <li>{} calculating diffs</li>
                    <li>{} performing sync</li>
                </ul>
            """,
            shorter_timedelta(self.duration),
            shorter_timedelta(self.source_load_time),
            self.source,
            shorter_timedelta(self.target_load_time),
            self.target,
            shorter_timedelta(self.diff_time),
            shorter_timedelta(self.sync_time),
        )


class SyncLogEntry(BaseModel):  # pylint: disable=nb-string-field-blank-null
    """Record of a single event during a data sync operation.

    Detailed sync logs are recorded in this model, rather than in JobResult.data, because
    JobResult.data imposes fairly strict expectations about the structure of its contents
    that do not align well with the requirements of this app. Also, storing log entries as individual
    database records rather than a single JSON blob allows us to filter, query, sort, etc. as desired.

    This model somewhat "shadows" Nautobot's built-in ObjectChange model; the key distinction to
    bear in mind is that an ObjectChange reflects a change that *did happen*, while a SyncLogEntry
    may reflect this or may reflect a change that *could not happen* or *failed*.
    Additionally, if we're syncing data from Nautobot to a different system as data target,
    the data isn't changing in Nautobot, so there will be no ObjectChange record.
    """

    sync = models.ForeignKey(to=Sync, on_delete=models.CASCADE, related_name="logs", related_query_name="log")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    action = models.CharField(max_length=32, choices=SyncLogEntryActionChoices)
    status = models.CharField(max_length=32, choices=SyncLogEntryStatusChoices)
    diff = models.JSONField(blank=True, null=True, encoder=DiffJSONEncoder)

    synced_object_type = models.ForeignKey(
        to=ContentType,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    synced_object_id = models.UUIDField(blank=True, null=True)
    synced_object = GenericForeignKey(ct_field="synced_object_type", fk_field="synced_object_id")

    object_repr = models.TextField(blank=True, default="", editable=False)

    message = models.TextField(blank=True)

    hide_in_diff_view = True

    class Meta:
        """Metaclass attributes of SyncLogEntry."""

        verbose_name_plural = "sync log entries"
        ordering = ["sync", "timestamp"]

    def get_action_class(self):
        """Map self.action to a Bootstrap label class."""
        return {
            SyncLogEntryActionChoices.ACTION_NO_CHANGE: "secondary",
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


@extras_features("export_templates", "graphql", "statuses")
class SyncRecord(BaseModel):
    """Record of a single object that was synced during a data sync operation.

    This model is primarily intended to support idempotency of sync operations,
    by recording which objects have already been synced from a given source to a given target.
    """

    sync = models.ForeignKey(
        to=Sync, on_delete=models.SET_NULL, related_name="records", related_query_name="record", null=True
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    module = models.CharField(max_length=CHARFIELD_MAX_LENGTH, help_text="Python module that Adapters reside in.")
    source_adapter = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, help_text="System data is read from", verbose_name="Source Adapter"
    )
    target_adapter = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, help_text="System data is written to", verbose_name="Target Adapter"
    )
    source_kwargs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Keyword arguments that were used to initialize the source adapter",
        verbose_name="Source Adapter Keyword Arguments",
    )
    target_kwargs = models.JSONField(
        default=dict,
        blank=True,
        help_text="Keyword arguments that were used to initialize the target adapter",
        verbose_name="Target Adapter Keyword Arguments",
    )
    diffsync_flags = EnumField(
        DiffSyncFlags,
        blank=True,
        null=True,
        help_text="Flags that were used to initialize the target adapter",
        verbose_name="DiffSync Flags",
        default=None,
    )
    obj_type = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, help_text="Type of the object that was diffed", verbose_name="Object Type"
    )
    obj_name = models.CharField(
        max_length=CHARFIELD_MAX_LENGTH, help_text="Name of the object that was diffed", verbose_name="Object Name"
    )
    obj_keys = models.JSONField(
        blank=True, null=True, help_text="Keys of the object that was diffed", verbose_name="Object Keys"
    )
    source_attrs = models.JSONField(
        blank=True,
        null=True,
        help_text="Source attributes of the object that was diffed",
        verbose_name="Source Attributes",
    )
    target_attrs = models.JSONField(
        blank=True,
        null=True,
        help_text="Target attributes of the object that was diffed",
        verbose_name="Target Attributes",
    )

    action = models.CharField(max_length=32, choices=SyncRecordActionChoices)
    status = StatusField(blank=False, null=False, verbose_name="Import Status")

    synced_object_type = models.ForeignKey(
        to=ContentType,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
    )
    synced_object_id = models.UUIDField(blank=True, null=True)
    synced_object = GenericForeignKey(ct_field="synced_object_type", fk_field="synced_object_id")
    parent = models.ForeignKey(
        to="self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="children",
        related_query_name="children",
    )
    message = models.TextField(blank=True, null=True, max_length=1024)

    def get_diff(self):
        """Compute a diff-like structure from source_attrs and target_attrs for rendering.

        Returns a dict in the format expected by render_diff template tag:
        {
            obj_type: {
                obj_name: {
                    "+": {attr: new_value},  # Attributes added or changed (target values)
                    "-": {attr: old_value}   # Attributes removed or changed (source values)
                }
            }
        }

        For CREATE: all attributes in source_attrs go to "+"
        For UPDATE: changed attributes appear in both "+" (new) and "-" (old)
        For DELETE: all attributes in target_attrs go to "-"
        """
        if not self.source_attrs and not self.target_attrs:
            return {}

        source_attrs = self.source_attrs or {}
        target_attrs = self.target_attrs or {}

        # Compute what changed: added, removed, or modified
        # "+" contains attributes that are in target (new/added values)
        # "-" contains attributes that are in source (old/removed values)
        added_or_changed = {}
        removed_or_changed = {}

        # For attributes in target: they are new/added/changed
        # If CREATE: target_attrs is empty, all source_attrs go to "+"
        # If UPDATE: changed values go to "+" (new) and "-" (old)
        for key, source_value in source_attrs.items():
            target_value = target_attrs.get(key)
            # If attribute doesn't exist in source or has different value, it's in target
            if key not in target_attrs or target_value != source_value:
                added_or_changed[key] = source_value
                # If it existed in source with different value, also track the old value
                if key in target_attrs:
                    removed_or_changed[key] = target_value

        # For attributes in target but not in source: they were removed
        # If DELETE: source_attrs is empty, all target_attrs go to "-"
        for key, target_value in target_attrs.items():
            if key not in source_attrs:
                removed_or_changed[key] = source_attrs.get(key)

        # Only include in diff if there are actual changes
        if not added_or_changed and not removed_or_changed:
            return {}

        diff = {
            self.obj_type: {
                self.obj_name: {
                    "+": added_or_changed,
                    "-": removed_or_changed,
                }
            }
        }
        return diff

    class Meta:
        """Metaclass attributes of SyncRecord."""

        unique_together = ("sync", "obj_name", "obj_type")
        ordering = ["timestamp"]

    def __str__(self):
        """String representation of a SyncRecord instance."""
        return f"{self.source_adapter} → {self.target_adapter}: {self.obj_type} {self.obj_name}"

    def get_ancestors(self, record=None):
        """Return a filterable QuerySet of all ancestors of a SyncRecord.

        Args:
            record (SyncRecord, optional): Child SyncRecord to traverse from. If not set, then this record (self) will be used.

        Returns:
            QuerySet: A QuerySet of all ancestor SyncRecords, ordered by timestamp.
        """
        if not record:
            record = self

        # Collect all ancestor primary keys by traversing up the parent chain
        ancestor_pks = []
        current_record = record

        while current_record.parent:
            parent_record = current_record.parent
            logger.debug("Processing SyncRecord %s...", parent_record)
            ancestor_pks.append(parent_record.pk)
            current_record = parent_record

        # Return a filterable QuerySet
        if ancestor_pks:
            return self.__class__.objects.filter(pk__in=ancestor_pks)
        return self.__class__.objects.none()

    def get_descendants(self, record=None):
        """
        Recursively return a filterable QuerySet of all descendants of a SyncRecord.

        Args:
            record (SyncRecord, optional): Parent SyncRecord to traverse from. If not set, then this record (self) will be used.

        Returns:
            QuerySet: A QuerySet of all descendant SyncRecords, ordered by timestamp.
        """
        if record is None:
            record = self

        # Collect all descendant primary keys by traversing down the tree
        descendant_pks = []
        records_to_process = [record]

        while records_to_process:
            current_record = records_to_process.pop(0)
            child_records = current_record.children.all()
            for child_record in child_records:
                logger.debug("Processing SyncRecord %s...", child_record)
                descendant_pks.append(child_record.pk)
                records_to_process.append(child_record)

        # Return a filterable QuerySet
        if descendant_pks:
            return self.__class__.objects.filter(pk__in=descendant_pks)
        return self.__class__.objects.none()


class SSOTConfig(models.Model):  # pylint: disable=nb-incorrect-base-class
    """Non-db model providing user permission constraints."""

    class Meta:
        managed = False
        default_permissions = ("view",)


__all__ = ("SSOTInfobloxConfig", "AutomationGatewayModel", "SSOTServiceNowConfig", "Sync", "SyncLogEntry", "SyncRecord")
