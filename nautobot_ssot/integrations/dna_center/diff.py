"""Custom Diff Class for custom handling of object CRUD operations."""

from collections import defaultdict

from diffsync.diff import Diff


class CustomOrderingDiff(Diff):
    """Alternate diff class to list children in alphabetical order, except devices to be ordered by CRUD action."""

    @classmethod
    def order_children_default(cls, children):
        """Simple diff to return all children in alphabetical order."""
        for child_name, _ in sorted(children.items()):
            yield children[child_name]

    @classmethod
    def order_children_area(cls, children):
        """Return a list of Areas sorted by top level and children."""
        children_by_level = defaultdict(list)

        created_areas = [area_name for area_name, area in children.items() if area.action == "create"]

        created_areas = sorted(created_areas, key=lambda s: (not s.endswith("__None"), s))

        # Organize the children's name by action create, update or delete and then by top level and children.
        for child_name, child in children.items():
            action = child.action or "skip"
            if action != "create":
                children_by_level[action].append(child_name)

        # Create a global list, organized per action, with deletion first to prevent conflicts
        sorted_children = sorted(children_by_level["delete"])
        sorted_children += created_areas
        sorted_children += sorted(children_by_level["update"])
        sorted_children += sorted(children_by_level["skip"])

        for name in sorted_children:
            yield children[name]
