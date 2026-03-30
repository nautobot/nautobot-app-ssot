"""Plugin template tags."""

from django import template
from django_jinja import library

register = template.Library()


@library.filter()
@register.filter()
def tree_position(value: int) -> str:
    """Used for rendering nested group position.

    Args:
        value (int): the index of the nesting

    Returns:
        str: table row string
    """
    if value == 0:
        return ""
    value = value - 1
    return "&nbsp;" * 4 * value + "&#8627; "
