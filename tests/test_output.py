from __future__ import annotations

import unittest
from argparse import Namespace
from pathlib import Path

from site_capture.cli import artifact_paths, crawl_row, nonnegative_int, parse_formats, positive_int, render_options
from site_capture.models import CaptureResult
from site_capture.output import page_dir_name


class OutputTests(unittest.TestCase):
    def test_page_dir_name_is_stable_and_safe(self) -> None:
        name = page_dir_name("https://example.com/pricing?plan=pro")
        self.assertRegex(name, r"^pricing-plan-pro-[a-f0-9]{10}$")
        self.assertEqual(name, page_dir_name("https://example.com/pricing?plan=pro"))

    def test_artifact_paths_can_be_relative_to_root(self) -> None:
        result = CaptureResult(url="https://example.com", markdown="page.md")
        artifacts = artifact_paths(result, Path("/tmp/capture/pages/home"), root=Path("/tmp/capture"))
        self.assertEqual(artifacts["markdown"], "pages/home/page.md")

    def test_crawl_row_includes_source(self) -> None:
        result = CaptureResult(url="https://example.com", markdown="page.md")
        row = crawl_row(result, Path("/tmp/capture/pages/home"), Path("/tmp/capture"), "reused")
        self.assertEqual(row["source"], "reused")
        self.assertEqual(row["artifact_dir"], "pages/home")

    def test_parse_format_aliases(self) -> None:
        self.assertEqual(parse_formats("md,png"), {"markdown", "screenshot"})
        self.assertEqual(parse_formats("all"), {"markdown", "screenshot", "html"})

    def test_int_validators(self) -> None:
        self.assertEqual(positive_int("1"), 1)
        self.assertEqual(nonnegative_int("0"), 0)
        with self.assertRaises(Exception):
            positive_int("0")
        with self.assertRaises(Exception):
            nonnegative_int("-1")

    def test_render_options_uses_mobile_device_defaults(self) -> None:
        args = Namespace(
            device="mobile",
            viewport_width=None,
            viewport_height=None,
            goto_timeout_ms=45000,
            load_timeout_ms=10000,
            wait_ms=500,
            scroll_steps=2,
            scroll_delay_ms=250,
            scroll_entire_page=True,
            remove_selector=[".newsletter-modal"],
        )
        render = render_options(args)
        self.assertEqual(render.device, "mobile")
        self.assertEqual(render.viewport_width, 390)
        self.assertEqual(render.viewport_height, 844)
        self.assertTrue(render.is_mobile)
        self.assertTrue(render.has_touch)
        self.assertTrue(render.scroll_entire_page)
        self.assertEqual(render.remove_selectors, (".newsletter-modal",))


if __name__ == "__main__":
    unittest.main()
