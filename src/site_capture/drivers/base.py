from __future__ import annotations

from typing import Protocol

from site_capture.models import CaptureJob, CaptureResult


class BrowserDriver(Protocol):
    name: str

    def start(self) -> None: ...

    def capture(self, job: CaptureJob) -> CaptureResult: ...

    def close(self) -> None: ...
