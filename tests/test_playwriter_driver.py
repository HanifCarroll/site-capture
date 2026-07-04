from __future__ import annotations

import unittest

from pathlib import Path

from site_capture.drivers.playwriter import PlaywriterDriver, count_sessions, parse_new_session_id
from site_capture.models import CaptureJob


class PlaywriterDriverTests(unittest.TestCase):
    def test_parse_new_session_id_from_status_output(self) -> None:
        output = 'Session 43 created. Use with: playwriter -s 43 -e "..."\n'
        self.assertEqual(parse_new_session_id(output), "43")

    def test_parse_new_session_id_from_plain_output(self) -> None:
        self.assertEqual(parse_new_session_id("abc-123\n"), "abc-123")

    def test_count_sessions(self) -> None:
        output = "ID  BROWSER\n----------\n1   Chrome\n2   Chrome\n"
        self.assertEqual(count_sessions(output), 2)

    def test_parse_result_with_log_prefix(self) -> None:
        driver = PlaywriterDriver(session="1")
        stdout = '[log] SITE_CAPTURE_RESULT {"url":"https://example.com/","ok":true,"links":[]}\n'
        result = driver._parse_result(
            CaptureJob(url="https://example.com/", output_dir=Path("/tmp/example"), formats={"markdown"}),
            stdout,
        )
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
