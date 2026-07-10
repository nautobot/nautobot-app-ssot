"""Template tags and filters for the Generic SSoT field mapping builder."""

from django import template

register = template.Library()


@register.filter
def get_item(container, key):
    """Look up a value by key (dict) or index (list) in a template.

    Usage:
        {{ my_dict|get_item:key_variable }}
        {{ my_list|get_item:forloop.counter0 }}
    """
    if isinstance(container, dict):
        return container.get(key, "")
    if isinstance(container, (list, tuple)):
        try:
            return container[int(key)]
        except (IndexError, ValueError, TypeError):
            return ""
    return ""


@register.filter
def multiply(value, arg):
    """Multiply value by arg.  Used for tree indentation pixel offsets."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0
