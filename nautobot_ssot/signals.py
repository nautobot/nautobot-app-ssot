"""Functions to perform actions when Django signals are called."""

STATUS_DICT = {
    "Pending": {"color": "66b3ff"},
    "Successful": {"color": "28a745"},
    "Failed": {"color": "f44336"},
    "Error": {"color": "dc3545"},
}


def nautobot_database_ready_callback(sender, *, apps, **kwargs):  # pylint: disable=unused-argument, too-many-locals
    """Ensure SyncRecord Statuses are in place and support SyncRecord ContentType.

    Callback function triggered by the nautobot_database_ready signal when the Nautobot database is fully ready.
    """
    # pylint: disable=invalid-name
    ContentType = apps.get_model("contenttypes", "ContentType")
    Status = apps.get_model("extras", "Status")
    SyncRecord = apps.get_model("nautobot_ssot", "SyncRecord")

    for status_option in ["Pending", "Successful", "Failed", "Error"]:
        _status = Status.objects.get_or_create(name=status_option)[0]
        _status.color = STATUS_DICT[status_option]["color"]
        _status.content_types.add(ContentType.objects.get_for_model(SyncRecord))
        _status.save()
