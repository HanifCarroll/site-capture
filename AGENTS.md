# Repository Instructions

This repo is a small Python CLI for capturing websites into durable artifacts.

- Keep the browser-control boundary inside `src/site_capture/drivers/`.
- Keep crawler behavior deterministic and resumable through per-page `meta.json` files.
- Do not commit captured site output, cookies, tokens, browser profiles, or private page content.
- Prefer stdlib code unless a dependency materially improves the CLI.
- Run `python -m unittest discover -s tests` before shipping changes.
