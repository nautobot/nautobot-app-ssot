"""Test Render_diff templatetags."""

import unittest
from nautobot_ssot.templatetags.render_diff import render_diff


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


@unittest.skip("TODO")
class TestRenderDiff(unittest.TestCase):
    """Tests for render_diff function."""

    def test_render_diff_as_expected(self):
        """Testing expected escaped and rendered HTML."""
        for input_dict, rendered_diff in test_params:
            with self.subTest():
                self.assertEqual(render_diff(input_dict), rendered_diff)
