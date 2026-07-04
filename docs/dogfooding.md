# Dogfooding Notes

## Round 1

Scenario: Run the installed CLI from `/tmp` as a first-time user.

Command:

```sh
site-capture --json crawl https://example.com --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The simplest crawl failed because `--out` was required.
- Help output did not show default flag values, so timeout/session/format behavior required README lookup.

Changes made:

- Made `--out` optional for `capture` and `crawl`.
- Added a predictable default output path: `./captures/<host>-<command>-<timestamp>`.
- Switched argparse help to show default values.

## Round 2

Scenario: Rerun the first-time crawl path after Round 1 from `/tmp`.

Command:

```sh
site-capture --json crawl https://example.com --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- The new default output worked, but help displayed `--out` as defaulting to `None`.
- The JSON result pointed to `pages.jsonl`, but a human or agent still had to open the ledger to find page artifacts.

Changes made:

- Hid meaningless `None` defaults in help output.
- Added `index.md` to crawl outputs.
- Added artifact path maps to capture results and crawl ledger rows.

## Round 3

Scenario: Check help, one-page capture JSON, crawl JSON, `index.md`, and `pages.jsonl` from `/tmp`.

Commands:

```sh
site-capture crawl --help
site-capture --json capture https://example.com --out /tmp/site-capture-round3-capture --formats markdown --scroll-steps 0 --wait-ms 100
site-capture --json crawl https://example.com --out /tmp/site-capture-round3-crawl --max-pages 1 --formats markdown --scroll-steps 0 --wait-ms 100
```

Observed friction:

- Successful fallback crawls looked warning-heavy when a site had no `robots.txt` or `/sitemap.xml`.
- `pages.jsonl` artifact paths were absolute, so moving a capture folder would make the ledger stale.

Changes made:

- Split expected discovery fallback messages into `notices`.
- Kept `warnings` for unexpected discovery or capture problems.
- Made crawl ledger artifact paths relative to the capture root.
