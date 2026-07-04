from __future__ import annotations

import unittest

from site_capture.output import page_dir_name


class OutputTests(unittest.TestCase):
    def test_page_dir_name_is_stable_and_safe(self) -> None:
        name = page_dir_name("https://example.com/pricing?plan=pro")
        self.assertRegex(name, r"^pricing-plan-pro-[a-f0-9]{10}$")
        self.assertEqual(name, page_dir_name("https://example.com/pricing?plan=pro"))


if __name__ == "__main__":
    unittest.main()
