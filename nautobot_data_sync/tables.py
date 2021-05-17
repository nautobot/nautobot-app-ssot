"""Data tables for data synchronization."""

from django_tables2 import Column, JSONColumn, LinkColumn, TemplateColumn

from nautobot.utilities.tables import BaseTable, ToggleColumn

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


ACTION_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_data_sync:synclogentry_list' %}?overview={{ record.id }}&action={{ action }}">
   {{ value }}
</a>
"""


STATUS_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_data_sync:synclogentry_list' %}?overview={{ record.id }}&status={{ status }}">
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
    created = LinkColumn(text=lambda sync: sync.job_result.created)
    name = Column(accessor="job_result.name")
    dry_run = TemplateColumn(template_code=DRY_RUN_LABEL, verbose_name="Sync?")

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
            "created",
            "name",
            "user",
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
            "created",
            "name",
            "dry_run",
            "num_created",
            "num_updated",
            "num_deleted",
            "num_failed",
            "num_errored",
            "message",
        )


ACTION_LABEL = """<span class="label label-{{ record.get_action_class }}">{{ record.action }}</span>"""


LOG_STATUS_LABEL = """<span class="label label-{{ record.get_status_class }}">{{ record.status }}</span>"""


class SyncLogEntryTable(BaseTable):
    """Table for displaying SyncLogEntry records."""

    pk = ToggleColumn()
    sync = Column(accessor="sync__id")
    action = TemplateColumn(template_code=ACTION_LABEL)
    diff = JSONColumn(orderable=False)
    status = TemplateColumn(template_code=LOG_STATUS_LABEL)
    message = TemplateColumn(template_code=MESSAGE_SPAN, orderable=False)

    class Meta(BaseTable.Meta):
        model = SyncLogEntry
        fields = ("pk", "timestamp", "sync", "action", "changed_object", "diff", "status", "message")
