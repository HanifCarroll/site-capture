# site-capture

`site-capture` is a Python CLI that captures websites into durable artifacts for agent workflows.

It is designed around a narrow contract:

1. Discover URLs from `robots.txt`, sitemap files, or a bounded same-origin crawl.
2. Ask a browser driver to render one URL at a time.
3. Save screenshots, Markdown, optional HTML, per-page metadata, and a crawl ledger.

The default driver is [`playwriter`](https://playwriter.dev), so the tool can use a real Chrome session controlled by Playwriter. An optional Playwright driver is available for public/static sites where a separate browser profile is enough.

## Install

From the repo:

```sh
python -m pip install .
```

For local development:

```sh
make install-local
site-capture --json doctor
```

## Commands

```sh
site-capture --json doctor
site-capture discover https://example.com --max-pages 50
site-capture capture https://example.com --out ./captures/example-home
site-capture crawl https://example.com --out ./captures/example --max-pages 100
```

If `--out` is omitted, `capture` and `crawl` write to `./captures/<host>-<command>-<timestamp>`.

Use Playwriter explicitly:

```sh
site-capture crawl https://example.com \
  --driver playwriter \
  --session auto \
  --out ./captures/example \
  --formats screenshot,markdown
```

Use an existing Playwriter session:

```sh
playwriter session list
site-capture crawl https://example.com --session 1 --out ./captures/example
```

Use Playwriter direct CDP mode:

```sh
site-capture crawl https://example.com --direct --out ./captures/example
site-capture crawl https://example.com --direct ws://localhost:9222/devtools/browser/... --out ./captures/example
```

Use the optional Playwright driver:

```sh
python -m pip install 'site-capture[playwright]'
playwright install
site-capture crawl https://example.com \
  --driver playwright \
  --playwright-profile ~/.site-capture/chrome-profile \
  --out ./captures/example
```

## Output Layout

```text
captures/example/
  manifest.json
  pages.jsonl
  pages/
    home-4be0d5625f/
      meta.json
      page.png
      page.md
      links.json
```

`manifest.json` summarizes the run. `pages.jsonl` is the machine-readable ledger agents should consume. Each page directory contains a `meta.json` file with the same stable shape:

```json
{
  "url": "https://example.com/",
  "final_url": "https://example.com/",
  "status": 200,
  "title": "Example",
  "ok": true,
  "driver": "playwriter",
  "screenshot": "page.png",
  "markdown": "page.md",
  "html": null,
  "links": ["https://example.com/about"],
  "warnings": [],
  "error": null,
  "session": "1"
}
```

`index.md` gives a human-readable table of captured pages and artifact links. In `pages.jsonl`, artifact paths are relative to the capture root so the folder can be moved.

On reruns, existing successful pages are reused unless `--force` is passed. Crawl output distinguishes `page_count`, fresh `captured_count`, and `reused_count`; each ledger row includes `source: "captured"` or `source: "reused"`.

## JSON Policy

`--json` writes JSON to stdout. Progress goes to stderr. Error output follows this shape:

```json
{"ok": false, "error": "message"}
```

The CLI never prints tokens or cookies intentionally. Captured page artifacts may contain private page content if your browser session can access it, so do not commit capture output.

## Formats

`--formats` accepts:

- `screenshot`: full-page PNG.
- `markdown`: Playwriter `getPageMarkdown` output when using the Playwriter driver; deterministic rendered-HTML conversion when using the Playwright driver.
- `html`: rendered HTML.

Aliases are accepted: `md` for `markdown`, `png` for `screenshot`, and `all` for every format.

Default:

```sh
--formats screenshot,markdown
```

## Notes

`site-capture` does not enforce `robots.txt` exclusion rules. It reads `robots.txt` only to find `Sitemap:` entries. Use it only on sites where you have permission or a legitimate reason to capture pages.

The crawler is intentionally bounded. Use `--max-pages`, `--delay-ms`, and `--allow-off-origin` explicitly when you need broader coverage.

## Development

```sh
make test
site-capture --help
site-capture --json doctor
```
