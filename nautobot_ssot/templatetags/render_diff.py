"""Template tag for rendering a DiffSync diff dictionary in a more human-readable form."""

from django import template
from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

_DIFF_PAGE_PARAM = "diff_page"
DEFAULT_DIFF_PAGE_SIZE = 50


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


def _build_page_url(request, page_num):
    """Build a URL for a specific diff page, preserving existing query parameters."""
    params = request.GET.copy()
    params[_DIFF_PAGE_PARAM] = page_num
    return f"?{params.urlencode()}"


def _render_pagination_controls(page_obj, request):
    """Return Bootstrap-compatible pagination HTML for the given page object."""
    if not page_obj.has_other_pages():
        return mark_safe("")  # noqa: S308

    paginator = page_obj.paginator
    current = page_obj.number
    num_pages = paginator.num_pages

    # Always show first, last, and a window around the current page
    pages_to_show = {1, num_pages} | set(range(max(1, current - 2), min(num_pages + 1, current + 3)))

    items_html = ""

    if page_obj.has_previous():
        prev_url = _build_page_url(request, page_obj.previous_page_number())
        items_html += format_html('<li class="page-item"><a class="page-link" href="{}">Previous</a></li>', prev_url)
    else:
        items_html += '<li class="page-item disabled"><span class="page-link">Previous</span></li>'

    prev_page = None
    for page_num in sorted(pages_to_show):
        if prev_page is not None and page_num - prev_page > 1:
            items_html += '<li class="page-item disabled"><span class="page-link">\u2026</span></li>'
        if page_num == current:
            items_html += format_html('<li class="page-item active"><span class="page-link">{}</span></li>', page_num)
        else:
            page_url = _build_page_url(request, page_num)
            items_html += format_html(
                '<li class="page-item"><a class="page-link" href="{}">{}</a></li>', page_url, page_num
            )
        prev_page = page_num

    if page_obj.has_next():
        next_url = _build_page_url(request, page_obj.next_page_number())
        items_html += format_html('<li class="page-item"><a class="page-link" href="{}">Next</a></li>', next_url)
    else:
        items_html += '<li class="page-item disabled"><span class="page-link">Next</span></li>'

    summary = format_html(
        '<p class="text-muted small">Showing {}\u2013{} of {} objects</p>',
        page_obj.start_index(),
        page_obj.end_index(),
        paginator.count,
    )

    return format_html(
        '<nav aria-label="Diff pagination"><ul class="pagination">{}</ul></nav>{}',
        mark_safe(items_html),  # noqa: S308
        summary,
    )


def render_diff_paginated(diff, request, per_page=DEFAULT_DIFF_PAGE_SIZE):
    """Render a paginated DiffSync diff dict to HTML with pagination controls.

    Flattens the diff into a list of top-level objects, paginates them, and renders
    only the current page. Falls back to a full render when the diff is small enough
    to fit on a single page.

    Args:
        diff: The diff dictionary to render.
        request: The current HTTP request (used for page number and URL building).
        per_page: Number of top-level diff objects per page (default 50).

    Returns:
        Safe HTML string with diff content and optional pagination controls.
    """
    if not diff:
        return format_html("<p>No diff data available.</p>")

    flat_items = _flatten_diff(diff)

    if len(flat_items) <= per_page:
        return render_diff(diff)

    try:
        page_num = int(request.GET.get(_DIFF_PAGE_PARAM, 1))
    except (TypeError, ValueError):
        page_num = 1

    paginator = Paginator(flat_items, per_page)
    try:
        page_obj = paginator.page(page_num)
    except (EmptyPage, InvalidPage):
        page_obj = paginator.page(paginator.num_pages)

    page_diff = _group_flat_items(list(page_obj.object_list))
    diff_html = render_diff(page_diff)
    pagination_html = _render_pagination_controls(page_obj, request)

    return format_html("{}{}", diff_html, pagination_html)
