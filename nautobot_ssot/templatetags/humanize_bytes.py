"""Simple template tag to render a shorter representation of a timedelta object."""

from django import template


register = template.Library()


@register.filter()
def humanize_bytes(size):
    """Humanize memory size given in bytes.

    Examples:
        1 => "1 B"
        1024 => "1 KiB"
        1024*1024 => "1 MiB"
    """
    suffix = "B"
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(size) < 1024.0:
            if round(size, 2) % 1 < 0.01:
                # If there are no relevant decimals "0.00" we skip them
                return f"{size:3.0f} {unit}{suffix}"
            return f"{size:3.2f} {unit}{suffix}"
        size /= 1024.0
    return f"{size:.1f} Yi{suffix}"
