"""Template tags for rendering expanded DiffSync diff with collapsible sections and lazy loading."""

import json

from django import template
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def render_diff_expanded_recursive(diff, level=0, parent_id="", section_counter=None, lazy_load=True, pk=None):
    """Recursively render a DiffSync diff dictionary with collapsible sections.

    Args:
        diff: The diff dictionary to render
        level: Current nesting level for indentation
        parent_id: ID of parent section for unique IDs
        section_counter: Counter for generating unique section IDs
        lazy_load: If True, only render section headers and lazy-load content
        pk: The Sync object's primary key for building lazy-load URLs

    Returns:
        HTML string with collapsible sections
    """
    if section_counter is None:
        section_counter = {"count": 0}

    result = ""

    for record_type, children in diff.items():
        section_counter["count"] += 1
        section_id = f"{parent_id}_section_{section_counter['count']}"

        # Count changes in this section
        changes = {"added": 0, "removed": 0, "modified": 0}
        for child, child_diffs in children.items():
            if "+" in child_diffs and "-" not in child_diffs:
                changes["added"] += 1
            elif "-" in child_diffs and "+" not in child_diffs:
                changes["removed"] += 1
            elif "+" in child_diffs and "-" in child_diffs:
                changes["modified"] += 1

        # Create section header with change counts
        change_summary = []
        if changes["added"] > 0:
            change_summary.append(f'{changes["added"]} Added')
        if changes["removed"] > 0:
            change_summary.append(f'{changes["removed"]} Removed')
        if changes["modified"] > 0:
            change_summary.append(f'{changes["modified"]} Modified')

        change_summary_html = " / ".join(change_summary)

        # Section header
        result += format_html('<div class="diff-section" data-level="{}">', level)

        result += format_html('<div class="diff-section-header" onclick="toggleSection(\'{}\')">', section_id)

        result += format_html(
            '<div class="diff-section-title">'
            '<i class="fa fa-chevron-right diff-toggle-icon" id="icon_{}"></i>'
            "<strong>{}</strong>"
            '<div class="diff-section-stats">{}</div>'
            "</div>",
            section_id,
            record_type,
            change_summary_html,
        )

        result += "</div>"  # Close diff-section-header

        # Section content - lazy load if enabled and we have a pk
        if lazy_load and pk is not None and level == 0:
            # For top-level sections, create lazy-load placeholder
            fetch_url = reverse(
                "plugins:nautobot_ssot:sync_diff_section",
                kwargs={"pk": pk, "record_type": record_type},
            )
            result += format_html(
                '<div class="diff-section-content" id="content_{}" style="display: none;" '
                'data-record-type="{}" data-fetch-url="{}" data-loaded="false"></div>',
                section_id,
                record_type,
                fetch_url,
            )
        else:
            # For nested sections or non-lazy mode, render content immediately
            result += format_html(
                '<div class="diff-section-content" id="content_{}" style="display: none;">', section_id
            )

            # Render children
            for child, child_diffs in children.items():
                section_counter["count"] += 1
                child_id = f"{section_id}_child_{section_counter['count']}"

                # Determine child class based on changes
                has_additions = "+" in child_diffs and child_diffs["+"]
                has_removals = "-" in child_diffs and child_diffs["-"]

                if has_additions and not has_removals:
                    child_class = "diff-added"
                    child_icon = "fa-plus-circle"
                elif has_removals and not has_additions:
                    child_class = "diff-subtracted"
                    child_icon = "fa-minus-circle"
                elif has_additions and has_removals:
                    child_class = "diff-changed"
                    child_icon = "fa-edit"
                else:
                    child_class = "diff-unchanged"
                    child_icon = "fa-circle"

                result += format_html('<div class="diff-item {}" data-child-id="{}">', child_class, child_id)

                # Child header
                result += format_html(
                    '<div class="diff-item-header" onclick="toggleItem(\'{}\')">'
                    '<i class="fa {} diff-item-icon" id="item_icon_{}"></i>'
                    '<span class="diff-item-name">{}</span>'
                    "</div>",
                    child_id,
                    child_icon,
                    child_id,
                    child,
                )

                # Child content
                result += format_html(
                    '<div class="diff-item-content" id="item_content_{}" style="display: none;">', child_id
                )

                # Render attributes
                for attr, value in child_diffs.pop("+", {}).items():
                    result += format_html(
                        '<div class="diff-attr diff-added">'
                        '<span class="diff-attr-name">+ {}</span>'
                        '<span class="diff-attr-value">{}</span>'
                        "</div>",
                        attr,
                        json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                    )

                for attr, value in child_diffs.pop("-", {}).items():
                    result += format_html(
                        '<div class="diff-attr diff-subtracted">'
                        '<span class="diff-attr-name">- {}</span>'
                        '<span class="diff-attr-value">{}</span>'
                        "</div>",
                        attr,
                        json.dumps(value) if isinstance(value, (dict, list)) else str(value),
                    )

                # Render nested diffs (always non-lazy for nested content)
                result += render_diff_expanded_recursive(
                    child_diffs, level + 1, child_id, section_counter, lazy_load=False, pk=None
                )

                result += "</div>"  # Close diff-item-content
                result += "</div>"  # Close diff-item

            result += "</div>"  # Close diff-section-content

        result += "</div>"  # Close diff-section

    return result


@register.simple_tag
def render_diff_expanded(diff, pk=None, lazy=True):
    """Render a DiffSync diff dict to HTML with collapsible sections."""
    if not diff:
        return format_html('<div class="alert alert-info">No diff data available</div>')

    html_text = render_diff_expanded_recursive(diff, lazy_load=lazy, pk=pk)
    return format_html('<div class="diff-expanded-container">{}</div>', mark_safe(html_text))  # noqa: S308


def render_section_children_html(children, level=0, parent_section_id=""):
    """Render the inner HTML for a section's children (used by lazy-loading view)."""
    section_counter = {"count": 0}
    result = ""

    # Render children
    for child, child_diffs in children.items():
        section_counter["count"] += 1
        child_id = f"{parent_section_id}_child_{section_counter['count']}"

        # Determine child class based on changes
        has_additions = "+" in child_diffs and child_diffs.get("+")
        has_removals = "-" in child_diffs and child_diffs.get("-")

        if has_additions and not has_removals:
            child_class = "diff-added"
            child_icon = "fa-plus-circle"
        elif has_removals and not has_additions:
            child_class = "diff-subtracted"
            child_icon = "fa-minus-circle"
        elif has_additions and has_removals:
            child_class = "diff-changed"
            child_icon = "fa-edit"
        else:
            child_class = "diff-unchanged"
            child_icon = "fa-circle"

        result += format_html('<div class="diff-item {}" data-child-id="{}">', child_class, child_id)

        # Child header
        result += format_html(
            '<div class="diff-item-header" onclick="toggleItem(\'{}\')">'
            '<i class="fa {} diff-item-icon" id="item_icon_{}"></i>'
            '<span class="diff-item-name">{}</span>'
            "</div>",
            child_id,
            child_icon,
            child_id,
            child,
        )

        # Child content
        result += format_html('<div class="diff-item-content" id="item_content_{}" style="display: none;">', child_id)

        # Create a copy of child_diffs to avoid mutating the original
        child_diffs_copy = child_diffs.copy()

        # Render attributes
        for attr, value in child_diffs_copy.pop("+", {}).items():
            result += format_html(
                '<div class="diff-attr diff-added">'
                '<span class="diff-attr-name">+ {}</span>'
                '<span class="diff-attr-value">{}</span>'
                "</div>",
                attr,
                json.dumps(value) if isinstance(value, (dict, list)) else str(value),
            )

        for attr, value in child_diffs_copy.pop("-", {}).items():
            result += format_html(
                '<div class="diff-attr diff-subtracted">'
                '<span class="diff-attr-name">- {}</span>'
                '<span class="diff-attr-value">{}</span>'
                "</div>",
                attr,
                json.dumps(value) if isinstance(value, (dict, list)) else str(value),
            )

        # Render nested diffs (non-lazy for nested content)
        result += render_diff_expanded_recursive(
            child_diffs_copy, level + 1, child_id, section_counter, lazy_load=False, pk=None
        )

        result += "</div>"  # Close diff-item-content
        result += "</div>"  # Close diff-item

    return result


@register.filter
def diff_stats(diff):
    """Calculate statistics for the diff."""
    if not diff:
        return {"total": 0, "added": 0, "removed": 0, "modified": 0}

    stats = {"total": 0, "added": 0, "removed": 0, "modified": 0}

    def count_changes(diff_data):
        if isinstance(diff_data, dict):
            for dict_name, child_diff_dict in diff_data.items():
                if child_diff_dict and isinstance(child_diff_dict, dict):
                    if "+" in child_diff_dict or "-" in child_diff_dict:
                        stats["total"] += 1
                    if "+" in child_diff_dict and "-" not in child_diff_dict:
                        stats["added"] += 1
                    elif "-" in child_diff_dict and "+" not in child_diff_dict:
                        stats["removed"] += 1
                    elif "+" in child_diff_dict and "-" in child_diff_dict:
                        stats["modified"] += 1
                # Recursively count nested changes
                count_changes(child_diff_dict)
        else:
            pass

    count_changes(diff)
    return stats


@register.simple_tag
def render_diff_json(diff):
    """Render diff as formatted JSON for debugging."""
    if not diff:
        return "No diff data"

    return format_html('<pre class="diff-json"><code>{}</code></pre>', json.dumps(diff, indent=2))
