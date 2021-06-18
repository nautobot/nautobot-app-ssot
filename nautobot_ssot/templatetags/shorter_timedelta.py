"""Simple template tag to render a shorter representation of a timedelta object."""

from django import template
from django.utils.html import format_html


register = template.Library()


@register.filter
def shorter_timedelta(timedelta):
    """Render a timedelta as "HH:MM:SS.d" instead of "HH:MM:SS.mmmmmm".

    Note that we don't bother with rounding.
    """
    if timedelta:
        prefix, microseconds = str(timedelta).split(".", 1)
        deciseconds = int(microseconds) // 100_000
        return f"{prefix}.{deciseconds}"
    return format_html("&mdash;")
