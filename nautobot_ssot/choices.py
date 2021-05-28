"""ChoiceSet classes for Single Source of Truth (SSoT)."""

from nautobot.utilities.choices import ChoiceSet


class SyncLogEntryActionChoices(ChoiceSet):
    """Valid values for a SyncLogEntry.action field."""

    ACTION_NO_CHANGE = "no-change"
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"

    CHOICES = (
        (ACTION_NO_CHANGE, "no change"),
        (ACTION_CREATE, "create"),
        (ACTION_UPDATE, "update"),
        (ACTION_DELETE, "delete"),
    )


class SyncLogEntryStatusChoices(ChoiceSet):
    """Valid values for a SyncLogEntry.status field."""

    STATUS_SUCCESS = "success"
    STATUS_FAILURE = "failure"
    STATUS_ERROR = "error"

    CHOICES = (
        (STATUS_SUCCESS, "succeeded"),
        (STATUS_FAILURE, "failed"),
        (STATUS_ERROR, "errored"),
    )
