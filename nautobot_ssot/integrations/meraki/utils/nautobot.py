"""Utility functions for working with Nautobot."""

from typing import List

from nautobot.extras.models import Note
from taggit.managers import TaggableManager


def get_tag_strings(list_tags: TaggableManager) -> List[str]:
    """Gets string values of all Tags in a list.

    This is the opposite of the `get_tags` function.

    Args:
        list_tags (TaggableManager): List of Tag objects to convert to strings.

    Returns:
        List[str]: List of string values matching the Tags passed in.
    """
    _strings = list(list_tags.names())
    if len(_strings) > 1:
        _strings.sort()
    return _strings


def update_note(nautobot_object, note: str, user, contenttype_id):
    """Make the Note on a Nautobot object match the note from Meraki.

    The Nautobot adapter loads the most recent Note on an object, so that same Note is the one
    updated in place here, or deleted when Meraki no longer has a note. Deleting is what makes the
    sync idempotent: an empty note used to be skipped, leaving the stale Note in Nautobot to be
    diffed again on every subsequent sync.

    Args:
        nautobot_object (Model): Nautobot object, such as a Device or Location, that the Note is assigned to.
        note (str): Note text from Meraki. An empty value removes the Note from the object.
        user (User): User to assign as the author of the Note.
        contenttype_id (UUID): ID of the ContentType for the passed Nautobot object.
    """
    current_note = nautobot_object.notes.last()
    if not note:
        if current_note:
            current_note.delete()
        return
    if current_note:
        current_note.note = note
        current_note.user = user
        current_note.validated_save()
        return
    new_note = Note(
        note=note,
        user=user,
        assigned_object_type_id=contenttype_id,
        assigned_object_id=nautobot_object.id,
    )
    new_note.validated_save()
