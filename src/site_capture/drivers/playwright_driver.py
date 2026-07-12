from __future__ import annotations

import json
from pathlib import Path

from site_capture.markdown import html_to_markdown
from site_capture.models import CaptureJob, CaptureResult, RenderOptions
from site_capture.output import write_json


class PlaywrightDriver:
    name = "playwright"

    def __init__(
        self,
        *,
        profile_dir: Path,
        headless: bool = False,
        channel: str = "chrome",
    ) -> None:
        self.profile_dir = profile_dir
        self.headless = headless
        self.channel = channel
        self._playwright = None
        self._context = None
        self._render_key: tuple[object, ...] | None = None

    def start(self, render: RenderOptions | None = None) -> None:
        render = render or RenderOptions()
        render_key = render_context_key(render)
        if self._context is not None and self._render_key == render_key:
            return
        if self._context is not None:
            self.close()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Playwright driver requires `pip install site-capture[playwright]` and `playwright install`.") from exc
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        options: dict[str, object] = {
            "user_data_dir": str(self.profile_dir),
            "channel": self.channel,
            "headless": self.headless,
            "viewport": {"width": render.viewport_width, "height": render.viewport_height},
            "device_scale_factor": render.device_scale_factor,
            "is_mobile": render.is_mobile,
            "has_touch": render.has_touch,
        }
        if render.user_agent:
            options["user_agent"] = render.user_agent
        self._context = self._playwright.chromium.launch_persistent_context(**options)
        self._render_key = render_key

    def capture(self, job: CaptureJob) -> CaptureResult:
        self.start(job.render)
        assert self._context is not None
        job.output_dir.mkdir(parents=True, exist_ok=True)
        page = self._context.new_page()
        warnings: list[str] = []
        status = None
        error = None
        try:
            response = page.goto(job.url, wait_until="domcontentloaded", timeout=job.render.goto_timeout_ms)
            status = response.status if response else None
            try:
                page.wait_for_load_state("networkidle", timeout=job.render.load_timeout_ms)
            except Exception as exc:  # noqa: BLE001 - load completeness is a warning, not a capture failure.
                warnings.append(f"Load wait issue: {exc}")
            if job.render.wait_ms:
                page.wait_for_timeout(job.render.wait_ms)
            if job.render.scroll_entire_page:
                page.evaluate(
                    """async (delayMs) => {
                        const step = Math.max(window.innerHeight * 0.8, 400);
                        for (let y = 0; y < document.documentElement.scrollHeight; y += step) {
                            window.scrollTo(0, y);
                            await new Promise((resolve) => window.setTimeout(resolve, delayMs));
                        }
                    }""",
                    job.render.scroll_delay_ms,
                )
            else:
                for _ in range(job.render.scroll_steps):
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(job.render.scroll_delay_ms)
            page.evaluate("() => window.scrollTo(0, 0)")
            for selector in job.render.remove_selectors:
                try:
                    removed_count = page.eval_on_selector_all(
                        selector,
                        "(elements) => { elements.forEach((element) => element.remove()); return elements.length; }",
                    )
                    if removed_count == 0:
                        warnings.append(f"Remove selector matched no elements: {selector}")
                except Exception as exc:  # noqa: BLE001 - invalid optional selectors should not discard the capture.
                    warnings.append(f"Remove selector issue for {selector!r}: {exc}")
        except Exception as exc:  # noqa: BLE001 - keep partial artifacts where possible.
            error = str(exc)
            warnings.append(f"Navigation issue: {exc}")

        final_url = page.url
        title = None
        try:
            title = page.title()
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Title issue: {exc}")

        screenshot = None
        markdown = None
        html = None
        rendered_html = ""
        if "html" in job.formats or "markdown" in job.formats:
            try:
                rendered_html = page.content()
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"HTML issue: {exc}")

        if "screenshot" in job.formats:
            try:
                page.screenshot(path=str(job.output_dir / "page.png"), full_page=True, scale="css")
                screenshot = "page.png"
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"Screenshot issue: {exc}")
        if "html" in job.formats and rendered_html:
            (job.output_dir / "page.html").write_text(rendered_html, encoding="utf-8")
            html = "page.html"
        if "markdown" in job.formats and rendered_html:
            (job.output_dir / "page.md").write_text(html_to_markdown(rendered_html, base_url=final_url), encoding="utf-8")
            markdown = "page.md"

        links: list[str] = []
        try:
            links = page.eval_on_selector_all("a[href]", "(anchors) => anchors.map((anchor) => anchor.href).filter(Boolean)")
            (job.output_dir / "links.json").write_text(json.dumps(links, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Link extraction issue: {exc}")
        page.close()

        ok = error is None and (status is None or 200 <= status < 400)
        result = CaptureResult(
            url=job.url,
            final_url=final_url,
            status=status,
            title=title,
            ok=ok,
            driver=self.name,
            device=job.render.device,
            viewport={"width": job.render.viewport_width, "height": job.render.viewport_height},
            screenshot=screenshot,
            markdown=markdown,
            html=html,
            links=links,
            warnings=warnings,
            error=error,
        )
        write_json(job.output_dir / "meta.json", result.to_dict())
        return result

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
            self._render_key = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None


def doctor() -> dict[str, object]:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return {
            "driver": "playwright",
            "available": False,
            "error": "Python package not installed",
        }
    return {
        "driver": "playwright",
        "available": True,
        "error": None,
    }


def render_context_key(render: RenderOptions) -> tuple[object, ...]:
    return (
        render.device,
        render.viewport_width,
        render.viewport_height,
        render.device_scale_factor,
        render.is_mobile,
        render.has_touch,
        render.user_agent,
        render.scroll_entire_page,
        render.remove_selectors,
    )
