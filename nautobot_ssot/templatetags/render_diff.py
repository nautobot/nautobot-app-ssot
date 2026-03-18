"""Template tag for rendering a DiffSync diff dictionary in a more human-readable form."""

from django import template
from django.core.paginator import EmptyPage, InvalidPage
from django.template.loader import get_template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from nautobot.apps.views import EnhancedPaginator
from nautobot.core.views.paginator import get_paginate_count

register = template.Library()

_PAGE_PARAM = "page"


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

            for attr, value in child_diffs.get("+", {}).items():
                child_result += format_html('<li class="diff-added">{}: {}</li>', attr, value)

            for attr, value in child_diffs.get("-", {}).items():
                child_result += format_html('<li class="diff-subtracted">{}: {}</li>', attr, value)

            nested = {k: v for k, v in child_diffs.items() if k not in ("+", "-")}
            if nested:
                child_result += render_diff_recursive(nested)

            child_result += "</ul></li>"
        result += format_html("<li>{}<ul>{}</ul></li>", record_type, mark_safe(child_result))  # noqa: S308
    return result


@register.simple_tag
def render_diff(diff):
    """Render a DiffSync diff dict to HTML."""
    if not diff:
        return ""
    html_text = render_diff_recursive(diff)
    return format_html("<ul>{}</ul>", mark_safe(html_text))  # noqa: S308


def _flatten_diff(diff):
    """Flatten a diff dict into a list of (model_type, obj_id, obj_diff) tuples."""
    items = []
    for model_type, children in diff.items():
        for obj_id, obj_diff in children.items():
            items.append((model_type, obj_id, obj_diff))
    return items


def _group_flat_items(flat_items):
    """Group flattened diff items back into a nested diff dict, preserving model_type order."""
    grouped = {}
    for model_type, obj_id, obj_diff in flat_items:
        grouped.setdefault(model_type, {})[obj_id] = obj_diff
    return grouped


def _render_pagination_controls(page_obj, request):
    """Render pagination controls using Nautobot's standard inc/paginator.html template."""
    if not page_obj.has_other_pages():
        return mark_safe("")  # noqa: S308

    tpl = get_template("inc/paginator.html")
    context = {"page": page_obj, "paginator": page_obj.paginator}
    return mark_safe(tpl.render(context, request))  # noqa: S308


def render_diff_paginated(diff, request):
    """Render a paginated DiffSync diff dict to HTML with pagination controls.

    Uses Nautobot's EnhancedPaginator and PAGINATE_COUNT setting to determine page
    size. Flattens the diff into a list of top-level objects, paginates them, and
    renders only the current page. Falls back to a full render when the diff fits
    on a single page.

    Args:
        diff: The diff dictionary to render.
        request: The current HTTP request (used for page count, page number, and URL building).

    Returns:
        Safe HTML string with diff content and optional pagination controls.
    """
    if not diff:
        return format_html("<p>No diff data available.</p>")

    per_page = get_paginate_count(request)
    flat_items = _flatten_diff(diff)

    if len(flat_items) <= per_page:
        return render_diff(diff)

    try:
        page_num = int(request.GET.get(_PAGE_PARAM, 1))
    except (TypeError, ValueError):
        page_num = 1

    paginator = EnhancedPaginator(flat_items, per_page)
    try:
        page_obj = paginator.page(page_num)
    except (EmptyPage, InvalidPage):
        page_obj = paginator.page(paginator.num_pages)

    page_diff = _group_flat_items(list(page_obj.object_list))
    diff_html = render_diff(page_diff)
    pagination_html = _render_pagination_controls(page_obj, request)

    return format_html("{}{}", diff_html, pagination_html)
