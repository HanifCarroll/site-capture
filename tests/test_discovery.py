from __future__ import annotations

import unittest
from unittest.mock import patch

from site_capture.discovery import discover_urls, filter_http_urls, normalize_url, read_sitemap, same_origin


SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/about#team</loc></url>
</urlset>
"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""


class DiscoveryTests(unittest.TestCase):
    def test_normalize_url_adds_scheme_and_removes_fragment(self) -> None:
        self.assertEqual(normalize_url("example.com/pricing#plans"), "https://example.com/pricing")

    def test_same_origin(self) -> None:
        self.assertTrue(same_origin("https://example.com/a", "https://example.com/b"))
        self.assertFalse(same_origin("https://example.com/a", "https://other.com/b"))

    def test_filter_http_urls(self) -> None:
        urls = filter_http_urls(
            ["/about", "mailto:test@example.com", "https://other.com/", "/about#team"],
            base_url="https://example.com",
        )
        self.assertEqual(urls, ["https://example.com/about"])

    @patch("site_capture.discovery.fetch_bytes")
    def test_read_urlset_sitemap(self, fetch_bytes) -> None:
        fetch_bytes.return_value = SITEMAP
        self.assertEqual(
            read_sitemap("https://example.com/sitemap.xml"),
            ["https://example.com/", "https://example.com/about"],
        )

    @patch("site_capture.discovery.fetch_bytes")
    def test_read_sitemap_index(self, fetch_bytes) -> None:
        fetch_bytes.side_effect = [SITEMAP_INDEX, SITEMAP]
        self.assertEqual(
            read_sitemap("https://example.com/sitemap.xml"),
            ["https://example.com/", "https://example.com/about"],
        )

    @patch("site_capture.discovery.fetch_bytes")
    def test_missing_robots_and_sitemap_are_notices(self, fetch_bytes) -> None:
        fetch_bytes.side_effect = [RuntimeError("HTTP 404"), RuntimeError("HTTP 404")]
        result = discover_urls("https://example.com", max_pages=1)
        self.assertEqual(result.urls, ["https://example.com/"])
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.notices), 3)


if __name__ == "__main__":
    unittest.main()
