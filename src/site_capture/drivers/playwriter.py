from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from site_capture.models import CaptureJob, CaptureResult
from site_capture.output import write_json


RESULT_PREFIX = "SITE_CAPTURE_RESULT "


class PlaywriterDriver:
    name = "playwriter"

    def __init__(
        self,
        *,
        command: str = "playwriter",
        session: str = "auto",
        timeout_ms: int = 90000,
        new_session_args: list[str] | None = None,
    ) -> None:
        self.command = command
        self.session = session
        self.timeout_ms = timeout_ms
        self.new_session_args = new_session_args or []
        self.created_session = False

    def start(self) -> None:
        if self.session != "auto":
            return
        proc = subprocess.run(
            [self.command, "session", "new", *self.new_session_args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"playwriter session new failed: {proc.stderr.strip() or proc.stdout.strip()}")
        session_id = parse_new_session_id(proc.stdout)
        if not session_id:
            raise RuntimeError(f"could not parse playwriter session id from: {proc.stdout.strip()!r}")
        self.session = session_id
        self.created_session = True

    def capture(self, job: CaptureJob) -> CaptureResult:
        self.start()
        job.output_dir.mkdir(parents=True, exist_ok=True)
        base_script = files("site_capture.drivers").joinpath("capture_playwriter.js").read_text(encoding="utf-8")
        temp_dir = Path(tempfile.mkdtemp(prefix="site-capture-playwriter-"))
        temp_script = temp_dir / "capture.js"
        payload = {
            "url": job.url,
            "formats": sorted(job.formats),
            "screenshotPath": str(temp_dir / "page.png"),
            "markdownFile": "page.md",
            "markdownPath": str(temp_dir / "page.md"),
            "htmlFile": "page.html",
            "htmlPath": str(temp_dir / "page.html"),
            "linksFile": "links.json",
            "linksPath": str(temp_dir / "links.json"),
            "viewport": {
                "width": job.render.viewport_width,
                "height": job.render.viewport_height,
            },
            "device": job.render.device,
            "deviceScaleFactor": job.render.device_scale_factor,
            "isMobile": job.render.is_mobile,
            "hasTouch": job.render.has_touch,
            "userAgent": job.render.user_agent,
            "gotoTimeoutMs": job.render.goto_timeout_ms,
            "loadTimeoutMs": job.render.load_timeout_ms,
            "waitMs": job.render.wait_ms,
            "scrollSteps": job.render.scroll_steps,
            "scrollDelayMs": job.render.scroll_delay_ms,
            "scrollEntirePage": job.render.scroll_entire_page,
            "removeSelectors": list(job.render.remove_selectors),
        }
        temp_script.write_text(
            f"globalThis.SITE_CAPTURE_JOB_OBJECT = {json.dumps(payload)};\n{base_script}",
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [self.command, "-s", str(self.session), "--timeout", str(self.timeout_ms), "-f", str(temp_script)],
                cwd=job.output_dir,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        finally:
            pass
        result = self._parse_result(job, proc.stdout)
        self._move_temp_artifacts(temp_dir, job.output_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
        result.session = str(self.session)
        if proc.returncode != 0:
            result.ok = False
            process_error = (proc.stderr.strip() or proc.stdout.strip() or f"playwriter exited {proc.returncode}")[-4000:]
            if result.error:
                result.warnings.append(process_error)
            else:
                result.error = process_error
        self._write_meta(job, result)
        return result

    def _move_temp_artifacts(self, temp_dir: Path, output_dir: Path) -> None:
        for filename in ("page.png", "page.md", "page.html", "links.json"):
            source = temp_dir / filename
            if source.exists():
                shutil.move(str(source), str(output_dir / filename))

    def close(self) -> None:
        return None

    def _parse_result(self, job: CaptureJob, stdout: str) -> CaptureResult:
        for line in reversed(stdout.splitlines()):
            marker = line.find(RESULT_PREFIX)
            if marker >= 0:
                data = json.loads(line[marker + len(RESULT_PREFIX) :])
                return CaptureResult(
                    url=str(data.get("url") or job.url),
                    final_url=data.get("final_url") if isinstance(data.get("final_url"), str) else None,
                    status=data.get("status") if isinstance(data.get("status"), int) else None,
                    title=data.get("title") if isinstance(data.get("title"), str) else None,
                    ok=bool(data.get("ok")),
                    driver=self.name,
                    device=str(data.get("device") or job.render.device),
                    viewport=data.get("viewport") if isinstance(data.get("viewport"), dict) else render_viewport(job),
                    screenshot=data.get("screenshot") if isinstance(data.get("screenshot"), str) else None,
                    markdown=data.get("markdown") if isinstance(data.get("markdown"), str) else None,
                    html=data.get("html") if isinstance(data.get("html"), str) else None,
                    links=[str(item) for item in data.get("links", []) if isinstance(item, str)],
                    warnings=[str(item) for item in data.get("warnings", []) if isinstance(item, str)],
                    error=data.get("error") if isinstance(data.get("error"), str) else None,
                )
        return CaptureResult(
            url=job.url,
            ok=False,
            driver=self.name,
            device=job.render.device,
            viewport=render_viewport(job),
            warnings=["playwriter did not return a SITE_CAPTURE_RESULT line"],
            error=stdout[-4000:] if stdout else "empty playwriter output",
        )

    def _write_meta(self, job: CaptureJob, result: CaptureResult) -> None:
        write_json(job.output_dir / "meta.json", result.to_dict())


def doctor(command: str = "playwriter") -> dict[str, object]:
    path = shutil.which(command)
    if not path:
        return {
            "driver": "playwriter",
            "available": False,
            "command": command,
            "path": None,
            "error": "command not found",
        }
    version = subprocess.run(
        [command, "-v"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sessions = subprocess.run(
        [command, "session", "list"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    session_count = count_sessions(sessions.stdout) if sessions.returncode == 0 else 0
    version_text = first_version_line(version.stdout, version.stderr)
    return {
        "driver": "playwriter",
        "available": version.returncode == 0,
        "command": command,
        "path": path,
        "version": version_text,
        "session_list_ok": sessions.returncode == 0,
        "active_session_count": session_count,
        "session_error": sessions.stderr.strip() if sessions.returncode != 0 else "",
    }


def count_sessions(output: str) -> int:
    count = 0
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("ID ") or set(stripped) == {"-"}:
            continue
        if stripped.split(maxsplit=1)[0].isdigit():
            count += 1
    return count


def first_version_line(stdout: str, stderr: str) -> str:
    for line in f"{stdout}\n{stderr}".splitlines():
        stripped = line.strip()
        if stripped.startswith("playwriter/"):
            return stripped
    return (stdout.strip() or stderr.strip()).splitlines()[0] if (stdout.strip() or stderr.strip()) else ""


def parse_new_session_id(output: str) -> str | None:
    match = re.search(r"\bSession\s+([A-Za-z0-9_.:-]+)\s+created\b", output)
    if match:
        return match.group(1)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) == 1 and re.match(r"^[A-Za-z0-9_.:-]+$", lines[0]):
        return lines[0]
    return None


def render_viewport(job: CaptureJob) -> dict[str, int]:
    return {"width": job.render.viewport_width, "height": job.render.viewport_height}
