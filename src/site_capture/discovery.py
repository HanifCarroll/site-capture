from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


USER_AGENT = "site-capture/0.1"


@dataclass
class DiscoveryResult:
    urls: list[str]
    sitemap_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url.strip())
    parsed = urlparse(clean)
    if not parsed.scheme:
        parsed = urlparse(f"https://{clean}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def same_origin(left: str, right: str) -> bool:
    a = urlparse(normalize_url(left))
    b = urlparse(normalize_url(right))
    return a.scheme == b.scheme and a.netloc == b.netloc


def filter_http_urls(urls: list[str], *, base_url: str | None = None, same_origin_only: bool = True) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for item in urls:
        if not item:
            continue
        absolute = urljoin(base_url, item) if base_url else item
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        normalized = normalize_url(absolute)
        if base_url and same_origin_only and not same_origin(base_url, normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(normalized)
    return filtered


def discover_urls(start_url: str, *, sitemap_url: str | None = None, max_pages: int = 200, timeout: int = 20) -> DiscoveryResult:
    start = normalize_url(start_url)
    warnings: list[str] = []
    sitemap_urls: list[str] = []
    candidates: list[str] = []
    if sitemap_url:
        candidates.append(normalize_url(sitemap_url))
    else:
        robots_sitemaps, robots_warnings = discover_sitemaps_from_robots(start, timeout=timeout)
        sitemap_urls.extend(robots_sitemaps)
        warnings.extend(robots_warnings)
        candidates.extend(robots_sitemaps)
        candidates.append(urljoin(start, "/sitemap.xml"))

    urls: list[str] = []
    seen_sitemaps: set[str] = set()
    for candidate in candidates:
        if candidate in seen_sitemaps:
            continue
        seen_sitemaps.add(candidate)
        sitemap_urls.append(candidate)
        try:
            urls.extend(read_sitemap(candidate, timeout=timeout))
        except Exception as exc:  # noqa: BLE001 - command output should retain the exact cause.
            warnings.append(f"Could not read sitemap {candidate}: {exc}")
        if len(urls) >= max_pages:
            break

    filtered = filter_http_urls(urls, base_url=start, same_origin_only=True)
    if not filtered:
        filtered = [start]
        warnings.append("No sitemap URLs found; seeded crawl with the start URL.")
    return DiscoveryResult(urls=filtered[:max_pages], sitemap_urls=dedupe(sitemap_urls), warnings=warnings)


def discover_sitemaps_from_robots(start_url: str, *, timeout: int = 20) -> tuple[list[str], list[str]]:
    parsed = urlparse(normalize_url(start_url))
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    warnings: list[str] = []
    try:
        text = fetch_bytes(robots_url, timeout=timeout).decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 - discovery should continue without robots.txt.
        return [], [f"Could not read robots.txt at {robots_url}: {exc}"]
    urls: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*sitemap\s*:\s*(\S+)\s*$", line, flags=re.IGNORECASE)
        if match:
            urls.append(normalize_url(match.group(1)))
    return dedupe(urls), warnings


def read_sitemap(sitemap_url: str, *, timeout: int = 20, max_sitemaps: int = 50) -> list[str]:
    visited: set[str] = set()
    urls: list[str] = []

    def visit(url: str) -> None:
        if url in visited or len(visited) >= max_sitemaps:
            return
        visited.add(url)
        content = fetch_bytes(url, timeout=timeout)
        if url.endswith(".gz") or content.startswith(b"\x1f\x8b"):
            content = gzip.decompress(content)
        root = ET.fromstring(content)
        name = local_name(root.tag)
        if name == "sitemapindex":
            for child in root:
                if local_name(child.tag) != "sitemap":
                    continue
                loc = child_text(child, "loc")
                if loc:
                    visit(normalize_url(loc))
        elif name == "urlset":
            for child in root:
                if local_name(child.tag) != "url":
                    continue
                loc = child_text(child, "loc")
                if loc:
                    urls.append(normalize_url(loc))
        else:
            raise ValueError(f"unsupported sitemap root <{name}>")

    visit(normalize_url(sitemap_url))
    return dedupe(urls)


def fetch_bytes(url: str, *, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def child_text(element: ET.Element, child_name: str) -> str | None:
    for child in element:
        if local_name(child.tag) == child_name and child.text:
            return child.text.strip()
    return None


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
