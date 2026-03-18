"""Test Render_diff templatetags."""

from django.test import RequestFactory
from nautobot.core.testing import TestCase

from nautobot_ssot.templatetags.render_diff import (
    _flatten_diff,
    _group_flat_items,
    render_diff,
    render_diff_paginated,
)

test_params = [
    (
        {
            "region": {
                "Catalonia": {"+": {"parent_name": None}, "-": {"parent_name": "Europe"}},
            }
        },
        '<ul><li>region<ul><li class="diff-changed">Catalonia<ul><li class="diff-added">parent_name: None</li><li class="diff-subtracted">parent_name: Europe</li></ul></li></ul></li></ul>',
    ),
    (
        {
            "region": {
                "Barcelona": {
                    "+": {
                        "cfs": {"asw_owner": ""},
                        "slug": "barcelona",
                        "description": "",
                        "parent_name": "Catalonia",
                    }
                },
            }
        },
        '<ul><li>region<ul><li class="diff-added">Barcelona<ul><li class="diff-added">cfs: {&#x27;asw_owner&#x27;: &#x27;&#x27;}</li><li class="diff-added">slug: barcelona</li><li class="diff-added">description: </li><li class="diff-added">parent_name: Catalonia</li></ul></li></ul></li></ul>',
    ),
    (
        {
            "model_name": {
                "element": {
                    "-": {
                        "cfs": {"this is a XSS": "<script>alert(document.cookie)</script>"},
                    }
                },
            }
        },
        '<ul><li>model_name<ul><li class="diff-subtracted">element<ul><li class="diff-subtracted">cfs: {&#x27;this is a XSS&#x27;: &#x27;&lt;script&gt;alert(document.cookie)&lt;/script&gt;&#x27;}</li></ul></li></ul></li></ul>',
    ),
    (
        {
            "model_name": {
                "element": {
                    "-": {
                        "description": "<script>alert(document.cookie)</script>",
                    }
                },
            }
        },
        '<ul><li>model_name<ul><li class="diff-subtracted">element<ul><li class="diff-subtracted">description: &lt;script&gt;alert(document.cookie)&lt;/script&gt;</li></ul></li></ul></li></ul>',
    ),
]


class TestRenderDiff(TestCase):
    """Tests for render_diff function."""

    def test_render_diff_as_expected(self):
        """Testing expected escaped and rendered HTML."""
        for input_dict, rendered_diff in test_params:
            with self.subTest():
                self.assertEqual(render_diff(input_dict), rendered_diff)

    def test_render_diff_empty(self):
        """Empty diff returns empty string."""
        self.assertEqual(render_diff({}), "")
        self.assertEqual(render_diff(None), "")


class TestFlattenGroupDiff(TestCase):
    """Tests for _flatten_diff and _group_flat_items helpers."""

    def test_flatten_diff(self):
        """Flatten produces (model_type, obj_id, obj_diff) tuples."""
        diff = {"region": {"ams": {"+": {}}, "nyc": {"-": {}}}}
        flat = _flatten_diff(diff)
        self.assertEqual(len(flat), 2)
        self.assertIn(("region", "ams", {"+": {}}), flat)
        self.assertIn(("region", "nyc", {"-": {}}), flat)

    def test_group_flat_items(self):
        """Grouped items reconstruct nested diff structure."""
        flat = [("region", "ams", {"+": {}}), ("region", "nyc", {"-": {}})]
        grouped = _group_flat_items(flat)
        self.assertEqual(grouped, {"region": {"ams": {"+": {}}, "nyc": {"-": {}}}})


class TestRenderDiffPaginated(TestCase):
    """Tests for render_diff_paginated function."""

    @classmethod
    def setUpTestData(cls):
        """Create a user for request context."""
        from django.contrib.auth import get_user_model  # pylint: disable=import-outside-toplevel

        cls.user = get_user_model().objects.create(username="test_render_diff_user")

    def setUp(self):
        """Create request factory for each test."""
        self.factory = RequestFactory()

    def _make_request(self, path="/", per_page=3, **query):
        """Create a GET request with user attached (required by get_paginate_count)."""
        params = {"per_page": str(per_page), **query}
        request = self.factory.get(path, params)
        request.user = self.user
        return request

    def test_empty_diff(self):
        """Empty diff returns no-data message."""
        request = self._make_request()
        result = render_diff_paginated({}, request)
        self.assertIn("No diff data available", str(result))

    def test_small_diff_no_pagination(self):
        """Diff with few items renders fully without pagination controls."""
        # 2 items, per_page=3 -> fits on one page
        diff = {"region": {"a": {}, "b": {}}}
        request = self._make_request()
        result = render_diff_paginated(diff, request)
        self.assertIn("region", str(result))
        self.assertIn("a", str(result))
        self.assertIn("b", str(result))
        # No pagination nav when single page
        self.assertNotIn("page=", str(result))

    def test_large_diff_paginated(self):
        """Diff with many items renders paginated."""
        # 5 items, per_page=3 -> 2 pages
        diff = {
            "region": {
                "a": {},
                "b": {},
                "c": {},
                "d": {},
                "e": {},
            }
        }
        request = self._make_request()
        result = render_diff_paginated(diff, request)
        self.assertIn("region", str(result))
        self.assertIn(" Showing ", str(result))
        self.assertIn("page=", str(result))

    def test_page_param_respected(self):
        """Requested page number is used."""
        diff = {"region": {f"x{i}": {} for i in range(5)}}
        request = self._make_request(page="2")
        result = render_diff_paginated(diff, request)
        self.assertIn("x3", str(result))
        self.assertIn("x4", str(result))
