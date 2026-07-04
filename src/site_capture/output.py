from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .models import CaptureResult


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def page_dir_name(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path in ("", "/"):
        stem = "home"
    else:
        stem = parsed.path.strip("/").split("/")[-1] or "page"
    if parsed.query:
        stem = f"{stem}-{parsed.query}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", stem).strip("-").lower() or "page"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:64]}-{digest}"


def result_from_meta(path: Path) -> CaptureResult:
    data = read_json(path)
    result = CaptureResult(
        url=str(data.get("url") or ""),
        final_url=data.get("final_url") if isinstance(data.get("final_url"), str) else None,
        status=data.get("status") if isinstance(data.get("status"), int) else None,
        title=data.get("title") if isinstance(data.get("title"), str) else None,
        ok=bool(data.get("ok")),
        driver=str(data.get("driver") or ""),
        screenshot=data.get("screenshot") if isinstance(data.get("screenshot"), str) else None,
        markdown=data.get("markdown") if isinstance(data.get("markdown"), str) else None,
        html=data.get("html") if isinstance(data.get("html"), str) else None,
        links=[str(item) for item in data.get("links", []) if isinstance(item, str)],
        warnings=[str(item) for item in data.get("warnings", []) if isinstance(item, str)],
        error=data.get("error") if isinstance(data.get("error"), str) else None,
        session=data.get("session") if isinstance(data.get("session"), str) else None,
    )
    return result


def relative_to(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
