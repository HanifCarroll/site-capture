from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


VALID_FORMATS = {"screenshot", "markdown", "html"}
FORMAT_ALIASES = {
    "md": "markdown",
    "png": "screenshot",
    "screen": "screenshot",
    "shot": "screenshot",
}


@dataclass(frozen=True)
class RenderOptions:
    device: str = "desktop"
    viewport_width: int = 1440
    viewport_height: int = 1200
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    user_agent: str | None = None
    goto_timeout_ms: int = 45000
    load_timeout_ms: int = 10000
    wait_ms: int = 500
    scroll_steps: int = 2
    scroll_delay_ms: int = 250


@dataclass(frozen=True)
class CaptureJob:
    url: str
    output_dir: Path
    formats: set[str]
    render: RenderOptions = field(default_factory=RenderOptions)


@dataclass
class CaptureResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    title: str | None = None
    ok: bool = False
    driver: str = ""
    device: str = "desktop"
    viewport: dict[str, int] | None = None
    screenshot: str | None = None
    markdown: str | None = None
    html: str | None = None
    links: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    session: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "title": self.title,
            "ok": self.ok,
            "driver": self.driver,
            "device": self.device,
            "viewport": self.viewport,
            "screenshot": self.screenshot,
            "markdown": self.markdown,
            "html": self.html,
            "links": self.links,
            "warnings": self.warnings,
            "error": self.error,
        }
        if self.session is not None:
            data["session"] = self.session
        return data
