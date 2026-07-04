from __future__ import annotations

import unittest

from site_capture.markdown import html_to_markdown


class MarkdownTests(unittest.TestCase):
    def test_basic_html_to_markdown(self) -> None:
        html = "<main><h1>Hello</h1><p>Visit <a href='/pricing'>pricing</a>.</p><script>bad()</script></main>"
        markdown = html_to_markdown(html, base_url="https://example.com")
        self.assertIn("# Hello", markdown)
        self.assertIn("[pricing](https://example.com/pricing)", markdown)
        self.assertNotIn("bad()", markdown)


if __name__ == "__main__":
    unittest.main()
