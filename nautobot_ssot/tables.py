"""Data tables for Single Source of Truth (SSOT) views."""

from django_tables2 import Column, DateTimeColumn, JSONColumn, LinkColumn, TemplateColumn

from nautobot.utilities.tables import BaseTable, ToggleColumn

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


ACTION_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_ssot:synclogentry_list' %}?overview={{ record.id }}&action={{ action }}">
   {{ value }}
</a>
"""


STATUS_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_ssot:synclogentry_list' %}?overview={{ record.id }}&status={{ status }}">
   {{ value }}
</a>
"""


DRY_RUN_LABEL = """
{% if record.dry_run %}
<span class="dry_run label label-default">Dry Run</span>
{% else %}
<span class="dry_run label label-info">Sync</span>
{% endif %}
"""


MESSAGE_SPAN = """<span class="message">{% if record.message %}{{ record.message }}{% else %}—{% endif %}</span>"""


class SyncTable(BaseTable):
    """Table for listing Sync records."""

    pk = ToggleColumn()
    timestamp = DateTimeColumn(accessor="job_result.created", linkify=True, short=True, verbose_name="Timestamp")
    name = Column(accessor="job_result.name")
    dry_run = TemplateColumn(template_code=DRY_RUN_LABEL, verbose_name="Sync?")
    status = TemplateColumn(template_code="{% include 'extras/inc/job_label.html' with result=record.job_result %}")

    num_unchanged = TemplateColumn(
        template_code=ACTION_LOGS_LINK,
        verbose_name="No change",
        extra_context={"link_class": "num_unchanged", "action": SyncLogEntryActionChoices.ACTION_NO_CHANGE},
    )
    num_created = TemplateColumn(
        template_code=ACTION_LOGS_LINK,
        verbose_name="Create",
        extra_context={"link_class": "num_created", "action": SyncLogEntryActionChoices.ACTION_CREATE},
    )
    num_updated = TemplateColumn(
        template_code=ACTION_LOGS_LINK,
        verbose_name="Update",
        extra_context={"link_class": "num_updated", "action": SyncLogEntryActionChoices.ACTION_UPDATE},
    )
    num_deleted = TemplateColumn(
        template_code=ACTION_LOGS_LINK,
        verbose_name="Delete",
        extra_context={"link_class": "num_deleted", "action": SyncLogEntryActionChoices.ACTION_DELETE},
    )

    num_succeeded = TemplateColumn(
        template_code=STATUS_LOGS_LINK,
        verbose_name="Success",
        extra_context={"link_class": "num_succeeded", "status": SyncLogEntryStatusChoices.STATUS_SUCCESS},
    )
    num_failed = TemplateColumn(
        template_code=STATUS_LOGS_LINK,
        verbose_name="Failure",
        extra_context={"link_class": "num_failed", "status": SyncLogEntryStatusChoices.STATUS_FAILURE},
    )
    num_errored = TemplateColumn(
        template_code=STATUS_LOGS_LINK,
        verbose_name="Error",
        extra_context={"link_class": "num_errored", "status": SyncLogEntryStatusChoices.STATUS_ERROR},
    )

    message = TemplateColumn(template_code=MESSAGE_SPAN, orderable=False)

    class Meta(BaseTable.Meta):
        model = Sync
        fields = (
            "pk",
            "timestamp",
            "name",
            "user",
            "status",
            "dry_run",
            "num_unchanged",
            "num_created",
            "num_updated",
            "num_deleted",
            "num_succeeded",
            "num_failed",
            "num_errored",
            "message",
        )
        default_columns = (
            "pk",
            "timestamp",
            "name",
            "status",
            "dry_run",
            "num_created",
            "num_updated",
            "num_deleted",
            "num_failed",
            "num_errored",
            "message",
        )
        order_by = ("-timestamp",)


ACTION_LABEL = """<span class="label label-{{ record.get_action_class }}">{{ record.action }}</span>"""


LOG_STATUS_LABEL = """<span class="label label-{{ record.get_status_class }}">{{ record.status }}</span>"""


class SyncLogEntryTable(BaseTable):
    """Table for displaying SyncLogEntry records."""

    pk = ToggleColumn()
    sync = LinkColumn(accessor="sync__id", verbose_name="Sync")
    action = TemplateColumn(template_code=ACTION_LABEL)
    diff = JSONColumn(orderable=False)
    status = TemplateColumn(template_code=LOG_STATUS_LABEL)
    message = TemplateColumn(template_code=MESSAGE_SPAN, orderable=False)
    changed_object = LinkColumn(verbose_name="Changed object")

    class Meta(BaseTable.Meta):
        model = SyncLogEntry
        fields = ("pk", "timestamp", "sync", "action", "changed_object", "diff", "status", "message")
        order_by = ("-timestamp",)
