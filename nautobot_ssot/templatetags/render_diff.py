from django import template
from django.utils.safestring import mark_safe


register = template.Library()


def render_diff_recursive(diff):
    result = ""
    for type, children in diff.items():
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
            child_result += f'<li class="{child_class}">{child}<ul>'

            for attr, value in child_diffs.pop("+", {}).items():
                child_result += f'<li class="diff-added">{attr}: {value}</li>'

            for attr, value in child_diffs.pop("-", {}).items():
                child_result += f'<li class="diff-subtracted">{attr}: {value}</li>'

            if child_diffs:
                child_result += render_diff_recursive(child_diffs)

            child_result += f"</ul></li>"
        child_result = f"<ul>{child_result}</ul>"
        result += f"<li>{type}{child_result}</li>"
    return result


@register.simple_tag
def render_diff(diff):
    """Render a DiffSync diff dict to HTML."""
    result = f"<ul>{render_diff_recursive(diff)}</ul>"

    return mark_safe(result)
