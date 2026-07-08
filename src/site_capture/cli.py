from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .discovery import discover_urls, filter_http_urls, normalize_url
from .drivers.playwriter import PlaywriterDriver
from .drivers.playwriter import doctor as playwriter_doctor
from .drivers.playwright_driver import PlaywrightDriver
from .drivers.playwright_driver import doctor as playwright_doctor
from .models import CaptureJob, CaptureResult, FORMAT_ALIASES, RenderOptions, VALID_FORMATS
from .output import default_output_dir, now_iso, page_dir_name, relative_to, result_from_meta, write_json, write_jsonl

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

DEVICE_PRESETS: dict[str, dict[str, object]] = {
    "desktop": {
        "viewport_width": 1440,
        "viewport_height": 1200,
        "device_scale_factor": 1.0,
        "is_mobile": False,
        "has_touch": False,
        "user_agent": None,
    },
    "mobile": {
        "viewport_width": 390,
        "viewport_height": 844,
        "device_scale_factor": 3.0,
        "is_mobile": True,
        "has_touch": True,
        "user_agent": MOBILE_USER_AGENT,
    },
}


class SmartDefaultsHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> str:
        if action.default is None or action.default is argparse.SUPPRESS:
            return action.help or ""
        return super()._get_help_string(action)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "discover":
            return command_discover(args)
        if args.command == "capture":
            return command_capture(args)
        if args.command == "crawl":
            return command_crawl(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level CLI must convert exceptions to stable output.
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    formatter = SmartDefaultsHelpFormatter
    parser = argparse.ArgumentParser(
        prog="site-capture",
        description="Capture websites into screenshots, Markdown, HTML, and JSON ledgers for agent workflows.",
        formatter_class=formatter,
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout.")
    parser.add_argument("--version", action="version", version=f"site-capture {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local driver availability.", formatter_class=formatter)
    add_driver_common(doctor)

    discover = subparsers.add_parser(
        "discover",
        help="List candidate URLs from robots.txt and sitemap files.",
        formatter_class=formatter,
    )
    discover.add_argument("url", help="Start URL.")
    discover.add_argument("--sitemap", help="Explicit sitemap URL.")
    discover.add_argument("--max-pages", type=positive_int, default=200, help="Maximum URLs to emit.")
    discover.add_argument("--timeout", type=positive_int, default=20, help="HTTP timeout in seconds for sitemap discovery.")

    capture = subparsers.add_parser("capture", help="Capture one URL into a directory.", formatter_class=formatter)
    capture.add_argument("url", help="URL to capture.")
    capture.add_argument("--out", help="Output directory for the page artifacts. Defaults to ./captures/<host>-capture-<timestamp>.")
    add_capture_options(capture)

    crawl = subparsers.add_parser("crawl", help="Capture a bounded same-origin site crawl.", formatter_class=formatter)
    crawl.add_argument("url", help="Start URL.")
    crawl.add_argument("--out", help="Output directory for the crawl artifacts. Defaults to ./captures/<host>-crawl-<timestamp>.")
    crawl.add_argument("--sitemap", help="Explicit sitemap URL.")
    crawl.add_argument("--max-pages", type=positive_int, default=200, help="Maximum pages to capture.")
    crawl.add_argument("--timeout", type=positive_int, default=20, help="HTTP timeout in seconds for sitemap discovery.")
    crawl.add_argument("--delay-ms", type=nonnegative_int, default=500, help="Delay between page captures.")
    crawl.add_argument("--force", action="store_true", help="Recapture pages that already have ok meta.json files.")
    crawl.add_argument("--allow-off-origin", action="store_true", help="Allow discovered links outside the start URL origin.")
    add_capture_options(crawl)
    return parser


def add_driver_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--driver", choices=["playwriter", "playwright", "all"], default="all", help="Driver to check.")
    parser.add_argument("--playwriter-command", default="playwriter", help="Playwriter command path.")


def add_capture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--driver", choices=["playwriter", "playwright"], default="playwriter", help="Browser driver.")
    parser.add_argument("--device", choices=sorted(DEVICE_PRESETS), default="desktop", help="Named device preset.")
    parser.add_argument(
        "--formats",
        default="screenshot,markdown",
        help="Comma-separated artifacts: screenshot, markdown, html. Aliases: md, png, all.",
    )
    parser.add_argument("--viewport-width", type=positive_int, help="Override browser viewport width.")
    parser.add_argument("--viewport-height", type=positive_int, help="Override browser viewport height.")
    parser.add_argument("--goto-timeout-ms", type=positive_int, default=45000, help="Navigation timeout.")
    parser.add_argument("--load-timeout-ms", type=positive_int, default=10000, help="Post-navigation load wait timeout.")
    parser.add_argument("--wait-ms", type=nonnegative_int, default=500, help="Extra wait before capture.")
    parser.add_argument("--scroll-steps", type=nonnegative_int, default=2, help="Scroll passes to trigger lazy content.")
    parser.add_argument("--scroll-delay-ms", type=nonnegative_int, default=250, help="Delay after each scroll pass.")
    parser.add_argument("--playwriter-command", default="playwriter", help="Playwriter command path.")
    parser.add_argument("--session", default="auto", help="Playwriter session ID, or auto to create one.")
    parser.add_argument("--playwriter-timeout-ms", type=positive_int, default=90000, help="Playwriter execution timeout.")
    parser.add_argument("--new-session-browser", choices=["headless", "cloud"], help="Pass --browser to playwriter session new.")
    parser.add_argument("--direct", nargs="?", const="", help="Pass --direct to playwriter session new, optionally with endpoint.")
    parser.add_argument("--patchright", action="store_true", help="Pass --patchright to playwriter session new.")
    parser.add_argument("--proxy", help="Pass --proxy to playwriter session new for cloud sessions.")
    parser.add_argument("--playwright-profile", help="Persistent profile directory for the Playwright driver.")
    parser.add_argument("--playwright-headless", action="store_true", help="Run the Playwright driver headless.")
    parser.add_argument("--playwright-channel", default="chrome", help="Playwright browser channel.")


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def command_doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, object]] = []
    if args.driver in {"playwriter", "all"}:
        checks.append(playwriter_doctor(args.playwriter_command))
    if args.driver in {"playwright", "all"}:
        checks.append(playwright_doctor())
    ok = all(bool(item.get("available")) for item in checks if item["driver"] == args.driver) if args.driver != "all" else any(
        bool(item.get("available")) for item in checks
    )
    payload = {
        "ok": ok,
        "version": __version__,
        "checks": checks,
    }
    return emit(args, payload, human=doctor_human(payload), code=0 if ok else 1)


def command_discover(args: argparse.Namespace) -> int:
    result = discover_urls(args.url, sitemap_url=args.sitemap, max_pages=args.max_pages, timeout=args.timeout)
    payload = {
        "ok": True,
        "start_url": normalize_url(args.url),
        "urls": result.urls,
        "count": len(result.urls),
        "sitemap_urls": result.sitemap_urls,
        "warnings": result.warnings,
        "notices": result.notices,
    }
    return emit(args, payload, human=discover_human(payload), code=0)


def command_capture(args: argparse.Namespace) -> int:
    formats = parse_formats(args.formats)
    driver = make_driver(args)
    render = render_options(args)
    output_dir = resolved_output_dir(args.out, args.url, command="capture")
    try:
        result = driver.capture(CaptureJob(url=normalize_url(args.url), output_dir=output_dir, formats=formats, render=render))
    finally:
        driver.close()
    payload = {
        "ok": result.ok,
        "result": result.to_dict(),
        "output_dir": str(output_dir),
        "artifacts": artifact_paths(result, output_dir),
        "device": render.device,
        "viewport": {"width": render.viewport_width, "height": render.viewport_height},
    }
    return emit(args, payload, human=capture_human(payload), code=0 if result.ok else 1)


def command_crawl(args: argparse.Namespace) -> int:
    formats = parse_formats(args.formats)
    root = resolved_output_dir(args.out, args.url, command="crawl")
    pages_root = root / "pages"
    pages_root.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    discovery = discover_urls(args.url, sitemap_url=args.sitemap, max_pages=args.max_pages, timeout=args.timeout)
    start_url = normalize_url(args.url)
    queue = list(discovery.urls)
    seen = set(queue)
    captured_pages: list[tuple[CaptureResult, Path, str]] = []
    driver = make_driver(args)
    render = render_options(args)
    try:
        index = 0
        while queue and len(captured_pages) < args.max_pages:
            url = queue.pop(0)
            index += 1
            page_dir = pages_root / page_dir_name(url)
            meta_path = page_dir / "meta.json"
            if meta_path.exists() and not args.force:
                existing = result_from_meta(meta_path)
                if existing.ok:
                    captured_pages.append((existing, page_dir, "reused"))
                    print_progress(args, f"skip {url}")
                    for link in filter_links(existing.links, start_url, args.allow_off_origin):
                        if link not in seen and len(seen) < args.max_pages:
                            seen.add(link)
                            queue.append(link)
                    continue
            print_progress(args, f"capture {index}/{args.max_pages} {url}")
            result = driver.capture(CaptureJob(url=url, output_dir=page_dir, formats=formats, render=render))
            captured_pages.append((result, page_dir, "captured"))
            for link in filter_links(result.links, start_url, args.allow_off_origin):
                if link not in seen and len(seen) < args.max_pages:
                    seen.add(link)
                    queue.append(link)
            if args.delay_ms > 0 and queue and len(captured_pages) < args.max_pages:
                time.sleep(args.delay_ms / 1000)
    finally:
        driver.close()

    results = [result for result, _page_dir, _source in captured_pages]
    rows = [crawl_row(result, page_dir, root, source) for result, page_dir, source in captured_pages]
    write_jsonl(root / "pages.jsonl", rows)
    write_crawl_index(root / "index.md", captured_pages, root)
    fresh_count = sum(1 for _result, _page_dir, source in captured_pages if source == "captured")
    reused_count = sum(1 for _result, _page_dir, source in captured_pages if source == "reused")
    manifest = {
        "ok": all(result.ok for result in results),
        "tool": "site-capture",
        "version": __version__,
        "started_at": started_at,
        "finished_at": now_iso(),
        "start_url": start_url,
        "driver": args.driver,
        "device": render.device,
        "viewport": {"width": render.viewport_width, "height": render.viewport_height},
        "formats": sorted(formats),
        "max_pages": args.max_pages,
        "page_count": len(results),
        "captured_count": fresh_count,
        "reused_count": reused_count,
        "ok_count": sum(1 for result in results if result.ok),
        "failed_count": sum(1 for result in results if not result.ok),
        "sitemap_urls": discovery.sitemap_urls,
        "warnings": discovery.warnings,
        "notices": discovery.notices,
    }
    write_json(root / "manifest.json", manifest)
    payload = {
        **manifest,
        "output_dir": str(root),
        "manifest": str(root / "manifest.json"),
        "pages_jsonl": str(root / "pages.jsonl"),
        "index_md": str(root / "index.md"),
    }
    return emit(args, payload, human=crawl_human(payload), code=0 if payload["ok"] else 1)


def make_driver(args: argparse.Namespace):
    if args.driver == "playwriter":
        new_session_args: list[str] = []
        if args.new_session_browser:
            new_session_args.extend(["--browser", args.new_session_browser])
        if args.direct is not None:
            new_session_args.append("--direct")
            if args.direct:
                new_session_args.append(args.direct)
        if args.patchright:
            new_session_args.append("--patchright")
        if args.proxy:
            new_session_args.extend(["--proxy", args.proxy])
        return PlaywriterDriver(
            command=args.playwriter_command,
            session=args.session,
            timeout_ms=args.playwriter_timeout_ms,
            new_session_args=new_session_args,
        )
    profile = Path(args.playwright_profile or "~/.site-capture/playwright-profile").expanduser()
    return PlaywrightDriver(profile_dir=profile, headless=args.playwright_headless, channel=args.playwright_channel)


def render_options(args: argparse.Namespace) -> RenderOptions:
    preset = DEVICE_PRESETS[args.device]
    viewport_width = args.viewport_width if args.viewport_width is not None else int(preset["viewport_width"])
    viewport_height = args.viewport_height if args.viewport_height is not None else int(preset["viewport_height"])
    return RenderOptions(
        device=args.device,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        device_scale_factor=float(preset["device_scale_factor"]),
        is_mobile=bool(preset["is_mobile"]),
        has_touch=bool(preset["has_touch"]),
        user_agent=preset["user_agent"] if isinstance(preset["user_agent"], str) else None,
        goto_timeout_ms=args.goto_timeout_ms,
        load_timeout_ms=args.load_timeout_ms,
        wait_ms=args.wait_ms,
        scroll_steps=args.scroll_steps,
        scroll_delay_ms=args.scroll_delay_ms,
    )


def resolved_output_dir(value: str | None, url: str, *, command: str) -> Path:
    path = Path(value).expanduser() if value else default_output_dir(normalize_url(url), command=command)
    return path.resolve()


def artifact_paths(result: CaptureResult, page_dir: Path, *, root: Path | None = None) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    if result.screenshot:
        artifacts["screenshot"] = artifact_path(page_dir / result.screenshot, root)
    if result.markdown:
        artifacts["markdown"] = artifact_path(page_dir / result.markdown, root)
    if result.html:
        artifacts["html"] = artifact_path(page_dir / result.html, root)
    links = page_dir / "links.json"
    if links.exists():
        artifacts["links"] = artifact_path(links, root)
    meta = page_dir / "meta.json"
    if meta.exists():
        artifacts["meta"] = artifact_path(meta, root)
    return artifacts


def crawl_row(result: CaptureResult, page_dir: Path, root: Path, source: str) -> dict[str, object]:
    row = result.to_dict()
    row["source"] = source
    row["artifact_dir"] = relative_to(page_dir, root)
    row["artifacts"] = artifact_paths(result, page_dir, root=root)
    return row


def artifact_path(path: Path, root: Path | None) -> str:
    if root is None:
        return str(path.resolve())
    return str(relative_to(path, root))


def write_crawl_index(path: Path, pages: list[tuple[CaptureResult, Path, str]], root: Path) -> None:
    lines = [
        "# Site Capture Index",
        "",
        f"Generated: {now_iso()}",
        "",
        "| Status | Source | Title | URL | Artifacts |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result, page_dir, source in pages:
        artifacts = []
        if result.markdown:
            artifacts.append(f"[Markdown]({relative_to(page_dir / result.markdown, root)})")
        if result.screenshot:
            artifacts.append(f"[Screenshot]({relative_to(page_dir / result.screenshot, root)})")
        if result.html:
            artifacts.append(f"[HTML]({relative_to(page_dir / result.html, root)})")
        artifacts.append(f"[Meta]({relative_to(page_dir / 'meta.json', root)})")
        lines.append(
            "| "
            + " | ".join(
                [
                    "ok" if result.ok else "failed",
                    source,
                    escape_table(result.title or ""),
                    escape_table(result.final_url or result.url),
                    ", ".join(artifacts),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def parse_formats(value: str) -> set[str]:
    requested = {item.strip().lower() for item in value.split(",") if item.strip()}
    if "all" in requested:
        requested.remove("all")
        requested.update(VALID_FORMATS)
    formats = {FORMAT_ALIASES.get(item, item) for item in requested}
    unknown = formats - VALID_FORMATS
    if unknown:
        allowed = ", ".join(sorted(VALID_FORMATS | set(FORMAT_ALIASES) | {"all"}))
        raise ValueError(f"unknown format(s): {', '.join(sorted(unknown))}; allowed: {allowed}")
    if not formats:
        raise ValueError("at least one format is required")
    return formats


def filter_links(links: list[str], start_url: str, allow_off_origin: bool) -> list[str]:
    return filter_http_urls(links, base_url=start_url, same_origin_only=not allow_off_origin)


def emit(args: argparse.Namespace, payload: dict[str, object], *, human: str, code: int) -> int:
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(human)
    return code


def print_progress(args: argparse.Namespace, message: str) -> None:
    if not args.json:
        print(message, file=sys.stderr)


def doctor_human(payload: dict[str, object]) -> str:
    lines = [f"site-capture {payload['version']}"]
    for check in payload["checks"]:  # type: ignore[index]
        assert isinstance(check, dict)
        state = "ok" if check.get("available") else "missing"
        lines.append(f"{check.get('driver')}: {state}")
        if check.get("version"):
            lines.append(f"  {check['version']}")
        if check.get("error"):
            lines.append(f"  {check['error']}")
    return "\n".join(lines)


def discover_human(payload: dict[str, object]) -> str:
    urls = [str(item) for item in payload.get("urls", [])]
    warnings = [str(item) for item in payload.get("warnings", [])]
    notices = [str(item) for item in payload.get("notices", [])]
    lines = [f"Discovered {len(urls)} URL(s)."]
    lines.extend(urls)
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    if notices:
        lines.append("")
        lines.append("Notices:")
        lines.extend(f"- {item}" for item in notices)
    return "\n".join(lines)


def capture_human(payload: dict[str, object]) -> str:
    result = payload["result"]
    assert isinstance(result, dict)
    artifacts = payload.get("artifacts", {})
    assert isinstance(artifacts, dict)
    state = "Captured" if result.get("ok") else "Capture failed"
    lines = [f"{state}: {result.get('url')}", f"Output: {payload['output_dir']}"]
    for label in ("markdown", "screenshot", "html", "meta", "links"):
        if label in artifacts:
            lines.append(f"{label}: {artifacts[label]}")
    return "\n".join(lines)


def crawl_human(payload: dict[str, object]) -> str:
    lines = [
        (
            f"Processed {payload.get('page_count', payload['captured_count'])} page(s): "
            f"{payload['captured_count']} captured, {payload.get('reused_count', 0)} reused, "
            f"{payload['ok_count']} ok, {payload['failed_count']} failed"
        ),
        f"Output: {payload['output_dir']}",
    ]
    for label in ("index_md", "manifest", "pages_jsonl"):
        if label in payload:
            lines.append(f"{label}: {payload[label]}")
    warnings = [str(item) for item in payload.get("warnings", [])]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines)
