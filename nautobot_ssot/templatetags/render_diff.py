"""Template tag for rendering a DiffSync diff dictionary in a more human-readable form."""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import format_html


register = template.Library()


def render_diff_recursive(diff):
    """Recursively render a DiffSync diff dictionary representation to nested list elements.

    Example:
        {
            location:
                ams:
                    +: {name: "Amsterdam"}
                    -: {name: "amsterdam"}
                    device:
                        ams01:
                            +: {}
        }

        would render as:

        * location
          ! ams
            + name: Amsterdam
            - name: amsterdam
            * device
              + ams01
    """
    result = ""
    for record_type, children in diff.items():
        child_result = ""
        for child, child_diffs in children.items():
            if "+" in child_diffs and "-" not in child_diffs:
                child_class = "diff-added"
            elif "-" in child_diffs and "+" not in child_diffs:
                child_class = "diff-subtracted"
            elif not child_diffs.get("+") and not child_diffs.get("-"):
                child_class = "diff-unchanged"
            else:
                child_class = "diff-changed"
            child_result += format_html('<li class="{}">{}<ul>', child_class, child)

            for attr, value in child_diffs.pop("+", {}).items():
                child_result += format_html('<li class="diff-added">{}: {}</li>', attr, value)

            for attr, value in child_diffs.pop("-", {}).items():
                child_result += format_html('<li class="diff-subtracted">{}: {}</li>', attr, value)

            if child_diffs:
                child_result += render_diff_recursive(child_diffs)

            child_result += "</ul></li>"
        result += format_html("<li>{}<ul>{}</ul></li>", record_type, mark_safe(child_result))  # nosec
    return result


@register.simple_tag
def render_diff(diff):
    """Render a DiffSync diff dict to HTML."""
    html_text = render_diff_recursive(diff)
    return format_html("<ul>{}</ul>", mark_safe(html_text))  # nosec
