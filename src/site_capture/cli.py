from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .discovery import DiscoveryResult, discover_urls, filter_http_urls, normalize_url
from .drivers.playwriter import PlaywriterDriver
from .drivers.playwriter import doctor as playwriter_doctor
from .drivers.playwright_driver import PlaywrightDriver
from .drivers.playwright_driver import doctor as playwright_doctor
from .models import CaptureJob, CaptureResult, RenderOptions, VALID_FORMATS
from .output import now_iso, page_dir_name, read_json, result_from_meta, write_json, write_jsonl


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
    parser = argparse.ArgumentParser(
        prog="site-capture",
        description="Capture websites into screenshots, Markdown, HTML, and JSON ledgers for agent workflows.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON to stdout.")
    parser.add_argument("--version", action="version", version=f"site-capture {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local driver availability.")
    add_driver_common(doctor)

    discover = subparsers.add_parser("discover", help="List candidate URLs from robots.txt and sitemap files.")
    discover.add_argument("url", help="Start URL.")
    discover.add_argument("--sitemap", help="Explicit sitemap URL.")
    discover.add_argument("--max-pages", type=int, default=200, help="Maximum URLs to emit.")
    discover.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds for sitemap discovery.")

    capture = subparsers.add_parser("capture", help="Capture one URL into a directory.")
    capture.add_argument("url", help="URL to capture.")
    capture.add_argument("--out", required=True, help="Output directory for the page artifacts.")
    add_capture_options(capture)

    crawl = subparsers.add_parser("crawl", help="Capture a bounded same-origin site crawl.")
    crawl.add_argument("url", help="Start URL.")
    crawl.add_argument("--out", required=True, help="Output directory for the crawl artifacts.")
    crawl.add_argument("--sitemap", help="Explicit sitemap URL.")
    crawl.add_argument("--max-pages", type=int, default=200, help="Maximum pages to capture.")
    crawl.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds for sitemap discovery.")
    crawl.add_argument("--delay-ms", type=int, default=500, help="Delay between page captures.")
    crawl.add_argument("--force", action="store_true", help="Recapture pages that already have ok meta.json files.")
    crawl.add_argument("--allow-off-origin", action="store_true", help="Allow discovered links outside the start URL origin.")
    add_capture_options(crawl)
    return parser


def add_driver_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--driver", choices=["playwriter", "playwright", "all"], default="all", help="Driver to check.")
    parser.add_argument("--playwriter-command", default="playwriter", help="Playwriter command path.")


def add_capture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--driver", choices=["playwriter", "playwright"], default="playwriter", help="Browser driver.")
    parser.add_argument(
        "--formats",
        default="screenshot,markdown",
        help="Comma-separated artifacts: screenshot, markdown, html.",
    )
    parser.add_argument("--viewport-width", type=int, default=1440, help="Browser viewport width.")
    parser.add_argument("--viewport-height", type=int, default=1200, help="Browser viewport height.")
    parser.add_argument("--goto-timeout-ms", type=int, default=45000, help="Navigation timeout.")
    parser.add_argument("--load-timeout-ms", type=int, default=10000, help="Post-navigation load wait timeout.")
    parser.add_argument("--wait-ms", type=int, default=500, help="Extra wait before capture.")
    parser.add_argument("--scroll-steps", type=int, default=2, help="Scroll passes to trigger lazy content.")
    parser.add_argument("--scroll-delay-ms", type=int, default=250, help="Delay after each scroll pass.")
    parser.add_argument("--playwriter-command", default="playwriter", help="Playwriter command path.")
    parser.add_argument("--session", default="auto", help="Playwriter session ID, or auto to create one.")
    parser.add_argument("--playwriter-timeout-ms", type=int, default=90000, help="Playwriter execution timeout.")
    parser.add_argument("--new-session-browser", choices=["headless", "cloud"], help="Pass --browser to playwriter session new.")
    parser.add_argument("--direct", nargs="?", const="", help="Pass --direct to playwriter session new, optionally with endpoint.")
    parser.add_argument("--patchright", action="store_true", help="Pass --patchright to playwriter session new.")
    parser.add_argument("--proxy", help="Pass --proxy to playwriter session new for cloud sessions.")
    parser.add_argument("--playwright-profile", help="Persistent profile directory for the Playwright driver.")
    parser.add_argument("--playwright-headless", action="store_true", help="Run the Playwright driver headless.")
    parser.add_argument("--playwright-channel", default="chrome", help="Playwright browser channel.")


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
    }
    return emit(args, payload, human=f"Discovered {len(result.urls)} URL(s).", code=0)


def command_capture(args: argparse.Namespace) -> int:
    formats = parse_formats(args.formats)
    driver = make_driver(args)
    render = render_options(args)
    output_dir = Path(args.out).expanduser().resolve()
    try:
        result = driver.capture(CaptureJob(url=normalize_url(args.url), output_dir=output_dir, formats=formats, render=render))
    finally:
        driver.close()
    payload = {"ok": result.ok, "result": result.to_dict(), "output_dir": str(output_dir)}
    return emit(args, payload, human=capture_human(result, output_dir), code=0 if result.ok else 1)


def command_crawl(args: argparse.Namespace) -> int:
    formats = parse_formats(args.formats)
    root = Path(args.out).expanduser().resolve()
    pages_root = root / "pages"
    pages_root.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    discovery = discover_urls(args.url, sitemap_url=args.sitemap, max_pages=args.max_pages, timeout=args.timeout)
    start_url = normalize_url(args.url)
    queue = list(discovery.urls)
    seen = set(queue)
    results: list[CaptureResult] = []
    driver = make_driver(args)
    render = render_options(args)
    try:
        index = 0
        while queue and len(results) < args.max_pages:
            url = queue.pop(0)
            index += 1
            page_dir = pages_root / page_dir_name(url)
            meta_path = page_dir / "meta.json"
            if meta_path.exists() and not args.force:
                existing = result_from_meta(meta_path)
                if existing.ok:
                    results.append(existing)
                    print_progress(args, f"skip {url}")
                    for link in filter_links(existing.links, start_url, args.allow_off_origin):
                        if link not in seen and len(seen) < args.max_pages:
                            seen.add(link)
                            queue.append(link)
                    continue
            print_progress(args, f"capture {index}/{args.max_pages} {url}")
            result = driver.capture(CaptureJob(url=url, output_dir=page_dir, formats=formats, render=render))
            results.append(result)
            for link in filter_links(result.links, start_url, args.allow_off_origin):
                if link not in seen and len(seen) < args.max_pages:
                    seen.add(link)
                    queue.append(link)
            if args.delay_ms > 0 and queue and len(results) < args.max_pages:
                time.sleep(args.delay_ms / 1000)
    finally:
        driver.close()

    rows = [result.to_dict() for result in results]
    write_jsonl(root / "pages.jsonl", rows)
    manifest = {
        "ok": all(result.ok for result in results),
        "tool": "site-capture",
        "version": __version__,
        "started_at": started_at,
        "finished_at": now_iso(),
        "start_url": start_url,
        "driver": args.driver,
        "formats": sorted(formats),
        "max_pages": args.max_pages,
        "captured_count": len(results),
        "ok_count": sum(1 for result in results if result.ok),
        "failed_count": sum(1 for result in results if not result.ok),
        "sitemap_urls": discovery.sitemap_urls,
        "warnings": discovery.warnings,
    }
    write_json(root / "manifest.json", manifest)
    payload = {**manifest, "output_dir": str(root), "pages_jsonl": str(root / "pages.jsonl")}
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
    return RenderOptions(
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        goto_timeout_ms=args.goto_timeout_ms,
        load_timeout_ms=args.load_timeout_ms,
        wait_ms=args.wait_ms,
        scroll_steps=args.scroll_steps,
        scroll_delay_ms=args.scroll_delay_ms,
    )


def parse_formats(value: str) -> set[str]:
    formats = {item.strip().lower() for item in value.split(",") if item.strip()}
    unknown = formats - VALID_FORMATS
    if unknown:
        raise ValueError(f"unknown format(s): {', '.join(sorted(unknown))}")
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


def capture_human(result: CaptureResult, output_dir: Path) -> str:
    state = "Captured" if result.ok else "Capture failed"
    return f"{state}: {result.url}\nOutput: {output_dir}"


def crawl_human(payload: dict[str, object]) -> str:
    return (
        f"Captured {payload['captured_count']} page(s): "
        f"{payload['ok_count']} ok, {payload['failed_count']} failed\n"
        f"Output: {payload['output_dir']}"
    )
