"""Data tables for Single Source of Truth (SSOT) views."""

from django_tables2 import Column, DateTimeColumn, JSONColumn, LinkColumn, TemplateColumn

from nautobot.apps.tables import BaseTable, ToggleColumn

from .choices import SyncLogEntryActionChoices, SyncLogEntryStatusChoices
from .models import Sync, SyncLogEntry


ACTION_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_ssot:synclogentry_list' %}?sync={{ record.id }}&action={{ action }}">
   {{ value }}
</a>
"""


STATUS_LOGS_LINK = """
<a class="{{ link_class }}"
   href="{% url 'plugins:nautobot_ssot:synclogentry_list' %}?sync={{ record.id }}&status={{ status }}">
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


class DashboardTable(BaseTable):  # pylint: disable=nb-sub-class-name
    """Abbreviated version of SyncTable, for use with the dashboard."""

    start_time = DateTimeColumn(linkify=True, short=True)
    source = Column(linkify=lambda record: record.get_source_url())
    target = Column(linkify=lambda record: record.get_target_url())
    status = TemplateColumn(template_code="{% include 'extras/inc/job_label.html' with result=record.job_result %}")
    dry_run = TemplateColumn(template_code=DRY_RUN_LABEL, verbose_name="Type")

    class Meta(BaseTable.Meta):
        """Metaclass attributes of DashboardTable."""

        model = Sync
        fields = ["source", "target", "start_time", "status", "dry_run"]  # pylint: disable=nb-use-fields-all
        order_by = ["-start_time"]


class SyncTable(BaseTable):
    """Table for listing Sync records."""

    pk = ToggleColumn()
    source = Column(linkify=lambda record: record.get_source_url())
    target = Column(linkify=lambda record: record.get_target_url())
    start_time = DateTimeColumn(linkify=True, short=True)
    duration = TemplateColumn(template_code="{% load shorter_timedelta %}{{ record.duration | shorter_timedelta }}")
    dry_run = TemplateColumn(template_code=DRY_RUN_LABEL, verbose_name="Type")
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

    class Meta(BaseTable.Meta):
        """Metaclass attributes of SyncTable."""

        model = Sync
        fields = (  # pylint: disable=nb-use-fields-all
            "pk",
            "source",
            "target",
            "start_time",
            "duration",
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
        )
        default_columns = (
            "pk",
            "source",
            "target",
            "start_time",
            "status",
            "dry_run",
            "num_created",
            "num_updated",
            "num_deleted",
            "num_failed",
            "num_errored",
        )
        order_by = ("-start_time",)


class SyncTableSingleSourceOrTarget(SyncTable):  # pylint: disable=nb-no-model-found
    """Subclass of SyncTable with fewer default columns."""

    class Meta(SyncTable.Meta):
        """Metaclass attributes of SyncTableSingleSourceOrTarget."""

        default_columns = (
            "start_time",
            "status",
            "dry_run",
            "num_unchanged",
            "num_created",
            "num_updated",
            "num_deleted",
            "num_failed",
            "num_errored",
        )


ACTION_LABEL = """<span class="label label-{{ record.get_action_class }}">{{ record.action }}</span>"""


LOG_STATUS_LABEL = """<span class="label label-{{ record.get_status_class }}">{{ record.status }}</span>"""


SYNCED_OBJECT = """
{% if record.synced_object %}
<a href="{{ record.synced_object.get_absolute_url}}">{{ record.synced_object}}</a>
{% else %}
{{ record.object_repr }}
{% endif %}
"""


class SyncLogEntryTable(BaseTable):
    """Table for displaying SyncLogEntry records."""

    pk = ToggleColumn()
    sync = LinkColumn(verbose_name="Sync")
    action = TemplateColumn(template_code=ACTION_LABEL)
    status = TemplateColumn(template_code=LOG_STATUS_LABEL)
    diff = JSONColumn(orderable=False)
    message = TemplateColumn(template_code=MESSAGE_SPAN, orderable=False)
    synced_object = TemplateColumn(template_code=SYNCED_OBJECT)

    class Meta(BaseTable.Meta):
        """Metaclass attributes of SyncLogEntryTable."""

        model = SyncLogEntry
        fields = (  # pylint: disable=nb-use-fields-all
            "pk",
            "timestamp",
            "sync",
            "action",
            "synced_object_type",
            "synced_object",
            "status",
            "diff",
            "message",
        )
        default_columns = ("pk", "timestamp", "sync", "action", "synced_object", "status", "diff", "message")
        order_by = ("-timestamp",)
